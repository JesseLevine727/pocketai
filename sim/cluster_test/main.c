/* PocketAI-T M1 acceptance firmware.
 *
 * Both harts boot the same image. They first complete a polling bootstrap,
 * then use machine-external interrupts for 10,000 sequence-checked mailbox
 * request/response rounds. Each hart also runs a deterministic integer and
 * stack-memory workload. Results are published at RESULT_BASE for the AXI
 * testbench (and eventually the PYNQ host) to verify before allowing halt.
 */
#include <stdint.h>

#define UART_OUT        0x00011000u
#define UART_CTRL       0x00011008u
#define MBOX_0_TO_1     0x00012000u
#define MBOX_1_TO_0     0x00012004u
#define MBOX_STATUS     0x00012008u
#define MBOX_ACK        0x0001200cu

#define RESULT_BASE     0x0000d000u
#define RESULT_DONE0    (RESULT_BASE + 0x00u)
#define RESULT_DONE1    (RESULT_BASE + 0x04u)
#define RESULT_COUNT0   (RESULT_BASE + 0x08u)
#define RESULT_COUNT1   (RESULT_BASE + 0x0cu)
#define RESULT_MSGSUM0  (RESULT_BASE + 0x10u)
#define RESULT_MSGSUM1  (RESULT_BASE + 0x14u)
#define RESULT_WORK0    (RESULT_BASE + 0x18u)
#define RESULT_WORK1    (RESULT_BASE + 0x1cu)
#define RESULT_ERROR0   (RESULT_BASE + 0x20u)
#define RESULT_ERROR1   (RESULT_BASE + 0x24u)
#define RESULT_READY0   (RESULT_BASE + 0x28u)
#define RESULT_READY1   (RESULT_BASE + 0x2cu)
#define RESULT_HOST_ACK (RESULT_BASE + 0x30u)

#define M1_ROUNDS       10000u
#define RESPONSE_XOR    0xa5a50000u
#define READY_FROM_0    0x48305244u
#define READY_FROM_1    0x48315244u
#define IRQ_READY_MAGIC 0x49525152u
#define DONE0_MAGIC     0x4d314830u
#define DONE1_MAGIC     0x4d314831u
#define HOST_ACK_MAGIC  0x484f5354u

#define EXPECTED_WORK0   0x29c4c2c2u
#define EXPECTED_WORK1   0xa3e316ecu
#define EXPECTED_MSGSUM0 0x468aad43u
#define EXPECTED_MSGSUM1 0x85558c0au

enum {
  ERR_UNEXPECTED_TRAP = 1u << 0,
  ERR_SPURIOUS_IRQ    = 1u << 1,
  ERR_SEQUENCE        = 1u << 2,
  ERR_BOOTSTRAP       = 1u << 3,
  ERR_WORKLOAD        = 1u << 4
};

static volatile uint32_t irq_count[2];
static volatile uint32_t irq_checksum[2];
static volatile uint32_t error_flags[2];

/* Reserve and initialize the complete AXI-visible result ABI in the ELF.
 * This prevents a stale RAM image from looking complete before firmware has
 * published both DONE words. The linker fixes this section at RESULT_BASE. */
static volatile uint32_t result_region[13]
    __attribute__((section(".results"), used)) = {0u};

_Static_assert(sizeof(result_region) == 0x34u,
               "M1 result ABI must occupy 13 words");

static inline void wr32(uint32_t addr, uint32_t value) {
  *(volatile uint32_t *)addr = value;
}

static inline uint32_t rd32(uint32_t addr) {
  return *(volatile uint32_t *)addr;
}

static inline uint32_t mhartid(void) {
  uint32_t id;
  __asm__ volatile("csrr %0, mhartid" : "=r"(id));
  return id;
}

static inline uint32_t rotl32(uint32_t value, uint32_t shift) {
  shift &= 31u;
  return shift == 0u ? value : (value << shift) | (value >> (32u - shift));
}

static inline uint32_t mix_checksum(uint32_t current, uint32_t value) {
  return rotl32(current ^ value, 5u) + 0x9e3779b9u;
}

static void uart_puts(const char *text) {
  while (*text != '\0') {
    wr32(UART_OUT, (uint32_t)*text++);
  }
}

static uint32_t core_workload(uint32_t seed) {
  uint32_t state = seed;
  uint32_t words[32];

  for (uint32_t i = 0; i < 32u; ++i) {
    state = state * 1664525u + 1013904223u;
    words[i] = state ^ (state >> 16);
  }

  for (uint32_t round = 0; round < 128u; ++round) {
    for (uint32_t i = 0; i < 32u; ++i) {
      uint32_t left = words[(i + 31u) & 31u];
      uint32_t right = words[(i + 1u) & 31u];
      state ^= state << 13;
      state ^= state >> 17;
      state ^= state << 5;
      words[i] = (words[i] + rotl32(left ^ right, i + round)) ^ state;
    }
  }

  uint32_t checksum = 0x811c9dc5u;
  for (uint32_t i = 0; i < 32u; ++i) {
    checksum = (checksum ^ words[i]) * 16777619u;
  }
  return checksum;
}

static inline void enable_mailbox_irq(void) {
  __asm__ volatile("csrs mie, %0" : : "r"(1u << 11) : "memory");
  __asm__ volatile("csrs mstatus, %0" : : "r"(1u << 3) : "memory");
}

static inline void disable_irqs(void) {
  __asm__ volatile("csrc mstatus, %0" : : "r"(1u << 3) : "memory");
}

/* GCC emits the register save/restore and mret sequence for this function. */
void machine_trap_handler(void)
    __attribute__((interrupt("machine"), aligned(4)));

void machine_trap_handler(void) {
  uint32_t cause;
  __asm__ volatile("csrr %0, mcause" : "=r"(cause));

  uint32_t hart = mhartid();
  if (hart > 1u) {
    hart = 0u;
  }
  if (cause != 0x8000000bu) {
    error_flags[hart] |= ERR_UNEXPECTED_TRAP;
    return;
  }

  uint32_t status = rd32(MBOX_STATUS);
  uint32_t pending_mask = hart == 0u ? 2u : 1u;
  if ((status & pending_mask) == 0u) {
    error_flags[hart] |= ERR_SPURIOUS_IRQ;
    return;
  }

  uint32_t value = rd32(hart == 0u ? MBOX_1_TO_0 : MBOX_0_TO_1);
  uint32_t next = irq_count[hart] + 1u;
  uint32_t expected = hart == 0u ? (next ^ RESPONSE_XOR) : next;
  if (value != expected) {
    error_flags[hart] |= ERR_SEQUENCE;
  }

  irq_checksum[hart] = mix_checksum(irq_checksum[hart], value);
  wr32(MBOX_ACK, pending_mask);
  irq_count[hart] = next;
}

static void bootstrap(uint32_t hart) {
  if (hart == 0u) {
    while ((rd32(MBOX_STATUS) & 2u) == 0u) {
    }
    if (rd32(MBOX_1_TO_0) != READY_FROM_1) {
      error_flags[0] |= ERR_BOOTSTRAP;
    }
    wr32(MBOX_ACK, 2u);
    wr32(MBOX_0_TO_1, READY_FROM_0);
    while ((rd32(MBOX_STATUS) & 1u) != 0u) {
    }
  } else {
    wr32(MBOX_1_TO_0, READY_FROM_1);
    while ((rd32(MBOX_STATUS) & 1u) == 0u) {
    }
    if (rd32(MBOX_0_TO_1) != READY_FROM_0) {
      error_flags[1] |= ERR_BOOTSTRAP;
    }
    wr32(MBOX_ACK, 1u);
    while ((rd32(MBOX_STATUS) & 2u) != 0u) {
    }
  }
}

void main(void) {
  uint32_t hart = mhartid();
  if (hart > 1u) {
    for (;;) {
      __asm__ volatile("wfi");
    }
  }

  bootstrap(hart);

  uint32_t work = core_workload(hart == 0u ? 0x12345678u : 0x9abcdef0u);
  uint32_t expected_work = hart == 0u ? EXPECTED_WORK0 : EXPECTED_WORK1;
  if (work != expected_work) {
    error_flags[hart] |= ERR_WORKLOAD;
  }

  irq_count[hart] = 0u;
  irq_checksum[hart] = hart == 0u ? 0x13579bdfu : 0x2468ace0u;

  if (hart == 0u) {
    uart_puts("H0 READY\n");
    wr32(RESULT_READY0, IRQ_READY_MAGIC);
    while (rd32(RESULT_READY1) != IRQ_READY_MAGIC) {
    }
    enable_mailbox_irq();

    for (uint32_t sequence = 1u; sequence <= M1_ROUNDS; ++sequence) {
      while ((rd32(MBOX_STATUS) & 1u) != 0u) {
      }
      wr32(MBOX_0_TO_1, sequence);
      while (irq_count[0] < sequence) {
        __asm__ volatile("wfi");
      }
    }

    disable_irqs();
    if (irq_checksum[0] != EXPECTED_MSGSUM0) {
      error_flags[0] |= ERR_SEQUENCE;
    }
    wr32(RESULT_COUNT0, irq_count[0]);
    wr32(RESULT_MSGSUM0, irq_checksum[0]);
    wr32(RESULT_WORK0, work);
    wr32(RESULT_ERROR0, error_flags[0]);
    __asm__ volatile("fence rw, rw" : : : "memory");
    wr32(RESULT_DONE0, DONE0_MAGIC);
  } else {
    while (rd32(RESULT_READY0) != IRQ_READY_MAGIC) {
    }
    uart_puts("H1 READY\n");
    enable_mailbox_irq();
    wr32(RESULT_READY1, IRQ_READY_MAGIC);

    for (uint32_t sequence = 1u; sequence <= M1_ROUNDS; ++sequence) {
      while (irq_count[1] < sequence) {
        __asm__ volatile("wfi");
      }
      while ((rd32(MBOX_STATUS) & 2u) != 0u) {
      }
      wr32(MBOX_1_TO_0, sequence ^ RESPONSE_XOR);
    }

    while ((rd32(MBOX_STATUS) & 2u) != 0u) {
    }
    disable_irqs();
    if (irq_checksum[1] != EXPECTED_MSGSUM1) {
      error_flags[1] |= ERR_SEQUENCE;
    }
    wr32(RESULT_COUNT1, irq_count[1]);
    wr32(RESULT_MSGSUM1, irq_checksum[1]);
    wr32(RESULT_WORK1, work);
    wr32(RESULT_ERROR1, error_flags[1]);
    __asm__ volatile("fence rw, rw" : : : "memory");
    wr32(RESULT_DONE1, DONE1_MAGIC);
  }

  if (hart == 1u) {
    while (rd32(RESULT_HOST_ACK) != HOST_ACK_MAGIC) {
    }
    wr32(UART_CTRL, 1u);
  }

  for (;;) {
    __asm__ volatile("wfi");
  }
}

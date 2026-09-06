/* Actual dual-Ibex translated-memory test; not the GPT-2 runtime. */
#include "memory_test_abi.h"
static volatile struct m5_test_result result[2]
    __attribute__((section(".results"))) = {{0}, {0}};
_Static_assert(sizeof(struct m5_test_result) == 64, "test result ABI");

static uint32_t pattern(uint32_t hart, uint32_t index) {
  return 0x51a00000u ^ (hart << 20) ^ (index * 0x10201u);
}
static uint32_t cycles(void) {
  uint32_t value;
  __asm__ volatile("csrr %0, mcycle" : "=r"(value));
  return value;
}
static void check(uint32_t hart, int condition, uint32_t bit) {
  if (!condition) result[hart].errors |= bit;
}

static void unaligned_case(uint32_t hart, uint32_t address, uint32_t value, int half) {
  volatile uint32_t *base = (volatile uint32_t *)(address & ~3u);
  uint32_t saved[2] = {base[0], base[1]};
  uint32_t got, signed_got = 0;
  if (half) {
    __asm__ volatile(".option push\n.option norvc\nsh %2, 0(%3)\nlhu %0, 0(%3)\nlh %1, 0(%3)\n.option pop"
        : "=&r"(got), "=&r"(signed_got) : "r"(value), "r"(address) : "memory");
    check(hart, got == (value & 65535u), 1024);
    check(hart, signed_got == (uint32_t)(int32_t)(int16_t)value, 4096);
  } else {
    __asm__ volatile(".option push\n.option norvc\nsw %1, 0(%2)\nlw %0, 0(%2)\n.option pop"
        : "=&r"(got) : "r"(value), "r"(address) : "memory");
    check(hart, got == value, 1024);
  }
  // Independent byte effects, including untouched lanes on both words.
  for (uint32_t byte = 0; byte < 8; ++byte) {
    uint32_t offset = address & 3u;
    uint32_t expected = (saved[byte / 4] >> (8 * (byte % 4))) & 255u;
    if (byte >= offset && byte < offset + (half ? 2u : 4u))
      expected = (value >> (8 * (byte - offset))) & 255u;
    check(hart, ((volatile uint8_t *)base)[byte] == expected, 2048);
  }
  base[0] = saved[0]; base[1] = saved[1];
  ++result[hart].unaligned_cases;
}

void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, cause, address, pc;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  __asm__ volatile("csrr %0, mcause" : "=r"(cause));
  __asm__ volatile("csrr %0, mtval" : "=r"(address));
  __asm__ volatile("csrr %0, mepc" : "=r"(pc));
  result[hart].traps++;
  result[hart].last_cause = cause;
  result[hart].last_address = address;
  result[hart].last_pc = pc;
  if (cause != result[hart].expected_cause || address != result[hart].expected_address) {
    result[hart].errors |= 0x80000000u;
    // Stop at the first unexpected trap; never turn it into an infinite stream
    // of secondary faults by blindly skipping an instruction of unknown size.
    *(volatile uint32_t *)0x00011008u = 1;
    for (;;) { __asm__ volatile("wfi"); }
  }
  // Every intentionally faulting access below is explicitly non-compressed.
  pc += 4;
  __asm__ volatile("csrw mepc, %0" :: "r"(pc) : "memory");
}

void m5_memory_main(uint32_t hart) {
  volatile uint32_t *page = (volatile uint32_t *)(0x40000000u + (hart << 12));
  result[hart].cycle_start = cycles();
  result[hart].state = 1;
  for (uint32_t i = 0; i < M5_TEST_WORDS; ++i) page[i] = pattern(hart, i);
  uint32_t checksum = 0;
  for (uint32_t j = 0; j < M5_TEST_WORDS; ++j) {
    uint32_t i = (j * 65u) & (M5_TEST_WORDS - 1u);
    uint32_t value = page[i];
    check(hart, value == pattern(hart, i), 1);
    checksum ^= value;
  }
  result[hart].checksum = checksum;
  // Explicit taken branch immediately after a slow DDR store. The branch's
  // comparison must not redirect before its second-cycle target calculation.
  uint32_t branch_result;
  __asm__ volatile(".option push\n.option norvc\nsw %1, 0(%2)\nbeq zero, zero, 1f\n"
                   "li %0, -1\nj 2f\n1: li %0, 0\n2:\n.option pop"
      : "=&r"(branch_result) : "r"(pattern(hart, 128)), "r"(&page[128]) : "memory");
  check(hart, branch_result == 0, 8192);
  result[hart].branch_cases = 1;
  page[0] = 0x11223344u;
  ((volatile uint8_t *)page)[1] = 0xaa;
  check(hart, page[0] == 0x1122aa44u, 2);
  ((volatile uint16_t *)page)[1] = 0xbbcc;
  check(hart, page[0] == 0xbbccaa44u, 4);
  check(hart, ((volatile int8_t *)page)[3] == -69, 8);
  check(hart, ((volatile int16_t *)page)[1] == -17460, 16);
  check(hart, ((volatile uint16_t *)page)[1] == 0xbbccu, 32);
  page[0] = pattern(hart, 0);
  for (uint32_t offset = 1; offset <= 3; ++offset) {
    uint32_t address = (uint32_t)page + 256u + offset;
    unaligned_case(hart, address, 0x89abcdefu ^ (hart << 20) ^ (offset << 8), 0);
    unaligned_case(hart, address, 0x000080a5u ^ (hart << 8) ^ offset, 1);
  }

  // The RO page contains addi a0,a0,7; ret: exercise instruction-port DDR too.
  uint32_t (*ddr_function)(uint32_t) = (uint32_t (*)(uint32_t))0x40002000u;
  check(hart, ddr_function(100 + hart) == 107 + hart, 64);
  result[hart].expected_cause = 7;
  result[hart].expected_address = 0x40002000u;
  __asm__ volatile(".option push\n.option norvc\nsw %0, 0(%1)\n.option pop"
                   :: "r"(0xdeadbeefu), "r"(0x40002000u) : "memory");
  check(hart, result[hart].traps == 1 && *(volatile uint32_t *)0x40002000u == 0x00750513u, 128);
  result[hart].expected_cause = 5;
  result[hart].expected_address = 0x40003000u;
  __asm__ volatile(".option push\n.option norvc\nlw zero, 0(%0)\n.option pop"
                   :: "r"(0x40003000u) : "memory");
  check(hart, result[hart].traps == 2, 256);
  result[hart].expected_address = 0x4ffffffcu;
  __asm__ volatile(".option push\n.option norvc\nlw zero, 0(%0)\n.option pop"
                   :: "r"(0x4ffffffcu) : "memory");
  check(hart, result[hart].traps == 3, 512);
  result[hart].state = 2;
  if (hart == 0) {
    while (result[1].state != 2) { }
    // Words at every offset and the offset-3 halfword span discontiguous pages.
    // The offset-1 word preserves the original failing LSU reproduction.
    for (uint32_t offset = 1; offset <= 3; ++offset) {
      unaligned_case(0, 0x40000ffcu + offset, 0x89abcdefu, 0);
      unaligned_case(0, 0x40000ffcu + offset, 0x0000abcd, 1);
    }
    result[0].cycle_end = cycles();
    result[0].state = 3;
    *(volatile uint32_t *)0x00011008u = 1;
  } else {
    result[1].cycle_end = cycles();
  }
}

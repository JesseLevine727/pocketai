/* Actual RV32IMC soft-binary64 qualification for M5 dynamic metadata. */
#include "pa_m5_numerics.h"
#include <stdint.h>
#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
struct result {
  uint32_t state, errors, norm_hash, affine_hash, dynamic_hash, round_hash;
  uint32_t storage_hash, factor, count, cycle_start, cycle_end, cause, address, pc, reserved[2];
};
static volatile struct result results[2] __attribute__((section(".results"))) = {{0}, {0}};
_Static_assert(sizeof(struct result) == 64, "result ABI");
static int16_t values[768], gain_q12[768];
static double gain[768], bias[768], scales[128];
static int32_t bias_q8[768];
static uint32_t multipliers[128];

static uint32_t cycles(void) {
  uint32_t value; __asm__ volatile("csrr %0, mcycle" : "=r"(value)); return value;
}
static uint32_t fnv(uint32_t hash, uint32_t value) {
  return (hash ^ value) * UINT32_C(16777619);
}
static void check(uint32_t hart, int okay, uint32_t bit) {
  if (!okay) results[hart].errors |= bit;
}
void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, value;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  __asm__ volatile("csrr %0, mcause" : "=r"(value)); results[hart].cause = value;
  __asm__ volatile("csrr %0, mtval" : "=r"(value)); results[hart].address = value;
  __asm__ volatile("csrr %0, mepc" : "=r"(value)); results[hart].pc = value;
  results[hart].errors |= UINT32_C(0x80000000); REG(0x11000u, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}

static void run(uint32_t hart) {
  for (uint32_t i = 0; i < 768; ++i) {
    values[i] = (int16_t)(((i * 101 + hart * 19) & 65535u) - 32768u);
    gain[i] = (double)((int32_t)((i * 37 + hart * 11) % 2001) - 1000) /
              (hart ? 64.0 : 128.0);
    bias[i] = (double)((int32_t)((i * 53 + hart * 7) % 1025) - 512) / 64.0;
  }
  uint32_t factor = 0;
  int64_t total = 0; uint64_t squares = 0;
  for (uint32_t i = 0; i < 768; ++i) {
    total += values[i]; squares += (uint64_t)((int64_t)values[i] * values[i]);
  }
  uint64_t variance = UINT64_C(768) * squares - (uint64_t)(total * total);
  double epsilon = 1.0e-5 * 65536.0 * (double)(768u * 768u);
  double divisor = (double)(UINT64_C(1) << (2 * (hart + 3)));
  union { double floating; uint64_t bits; } correction = {
      .floating = pa_m5_sqrt_f64(((double)variance + epsilon) /
                                 ((double)variance + epsilon / divisor))};
  results[hart].reserved[0] = (uint32_t)correction.bits;
  results[hart].reserved[1] = (uint32_t)(correction.bits >> 32);
  check(hart, pa_m5_layernorm_metadata(values, 768, hart + 3, gain, bias,
                                       gain_q12, bias_q8, &factor) == 0, 1);
  uint32_t hash = UINT32_C(2166136261);
  for (uint32_t i = 0; i < 768; ++i) {
    hash = fnv(hash, (uint16_t)gain_q12[i]); hash = fnv(hash, (uint32_t)bias_q8[i]);
  }
  hash = fnv(hash, factor); results[hart].norm_hash = hash; results[hart].factor = factor;
  check(hart, hash == (hart ? UINT32_C(0x783a8841) : UINT32_C(0x96dc8a24)), 2);

  for (uint32_t i = 0; i < 128; ++i)
    scales[i] = (double)(((i * 97 + hart * 31) % 10000) + 1) / 4096.0;
  uint32_t shift = 0;
  check(hart, pa_m5_affine_metadata(scales, 128, multipliers, &shift) == 0, 4);
  hash = UINT32_C(2166136261);
  for (uint32_t i = 0; i < 128; ++i) hash = fnv(hash, multipliers[i]);
  hash = fnv(hash, shift); results[hart].affine_hash = hash;
  check(hart, shift == 29 && hash == (hart ? UINT32_C(0x92a2e908) : UINT32_C(0xc712e908)), 8);

  hash = UINT32_C(2166136261);
  for (uint32_t maximum = hart; maximum <= 32768; maximum += 37 + hart)
    hash = fnv(hash, pa_m5_dynamic_multiplier(maximum));
  results[hart].dynamic_hash = hash;
  check(hart, hash == (hart ? UINT32_C(0xb80bb28e) : UINT32_C(0xdbf0ab4f)), 16);

  hash = UINT32_C(2166136261);
  for (int32_t i = 0; i < 4096; ++i)
    hash = fnv(hash, (uint32_t)pa_m5_rne_f64_signed((double)(i - 2048) / 2.0));
  union { uint64_t bits; double floating; } negative_zero = {
      .bits = UINT64_C(0x8000000000000000)};
  check(hart, pa_m5_rne_f64(negative_zero.floating) == 0 &&
              pa_m5_rne_f64_signed(negative_zero.floating) == 0, 128);
  results[hart].round_hash = hash; check(hart, hash == UINT32_C(0x208555c5), 32);

  hash = UINT32_C(2166136261);
  for (uint32_t i = 0; i < 1024; ++i)
    hash = fnv(hash, pa_m5_storage_exponent((double)(i + 1) * 32700.0 / 256.0));
  results[hart].storage_hash = hash; check(hart, hash == UINT32_C(0xe62eb74a), 64);
  results[hart].count = 768 + 128 + (32769 - hart + 36 + hart) / (37 + hart) + 4096 + 1024 + 2;
}

void m5_memory_main(uint32_t hart) {
  results[hart].cycle_start = cycles(); results[hart].state = 1;
  // One shared bounded workspace: the harts deliberately take turns.
  if (hart == 1) while (results[0].state != 2) __asm__ volatile("nop");
  run(hart); results[hart].cycle_end = cycles();
  __asm__ volatile("fence rw, rw" ::: "memory"); results[hart].state = 2;
  if (hart == 0) {
    while (results[1].state != 2) __asm__ volatile("nop");
    results[0].state = 3; REG(0x11000u, 8) = 1;
  }
  for (;;) __asm__ volatile("wfi");
}

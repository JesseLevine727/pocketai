/* Run independently calculated M-extension results on BOTH real harts, then
 * the original memory/unaligned/branch/trap/reset regression without edits. */
#define m5_memory_main m5_original_memory_main
#include "../m5/memory_test.c"
#undef m5_memory_main

static uint64_t soft_product(uint32_t a, uint32_t b) {
  uint64_t sum = 0, shifted = a;
  for (uint32_t i = 0; i < 32; ++i) {
    if (b & 1) sum += shifted;
    shifted <<= 1; b >>= 1;
  }
  return sum;
}
static uint32_t soft_div(uint32_t a, uint32_t b, uint32_t *rem) {
  uint64_t r = 0; uint32_t q = 0;
  for (uint32_t i = 32; i; --i) {
    r = (r << 1) | ((a >> (i - 1)) & 1);
    if (r >= b) { r -= b; q |= UINT32_C(1) << (i - 1); }
  }
  *rem = (uint32_t)r; return q;
}
static void arithmetic_pair(uint32_t hart, uint32_t a, uint32_t b) {
  uint64_t product = soft_product(a, b);
  uint32_t low, high, hsu, hu, div, divu, rem, remu, dep;
  // Include a pending translated DDR store immediately before M operations;
  // dependent MUL and taken branch exercise result forwarding/control.
  volatile uint32_t *page = (volatile uint32_t *)(0x40000000u + (hart << 12));
  __asm__ volatile("sw %[a], 0(%[page])\n"
                   "mul %[lo], %[a], %[b]\n"
                   "mul %[dep], %[lo], %[b]\n"
                   "beq %[dep], zero, 1f\nnop\n1:\n"
                   "mulh %[hi], %[a], %[b]\n"
                   "mulhsu %[hsu], %[a], %[b]\n"
                   "mulhu %[hu], %[a], %[b]\n"
                   "div %[div], %[a], %[b]\n"
                   "divu %[divu], %[a], %[b]\n"
                   "rem %[rem], %[a], %[b]\n"
                   "remu %[remu], %[a], %[b]\n"
      : [lo] "=&r"(low), [dep] "=&r"(dep), [hi] "=&r"(high),
        [hsu] "=&r"(hsu), [hu] "=&r"(hu), [div] "=&r"(div),
        [divu] "=&r"(divu), [rem] "=&r"(rem), [remu] "=&r"(remu)
      : [a] "r"(a), [b] "r"(b), [page] "r"(page) : "memory");
  uint32_t expected_hu = (uint32_t)(product >> 32);
  check(hart, low == (uint32_t)product && hu == expected_hu &&
        hsu == expected_hu - ((a >> 31) ? b : 0) &&
        high == expected_hu - ((a >> 31) ? b : 0) - ((b >> 31) ? a : 0) &&
        dep == (uint32_t)soft_product((uint32_t)product, b), 0x10000);
  uint32_t ur, uq = soft_div(a, b, &ur);
  uint32_t sr, sq = soft_div((a >> 31) ? 0u-a : a, (b >> 31) ? 0u-b : b, &sr);
  if ((a ^ b) >> 31) sq = 0u - sq;
  if (a >> 31) sr = 0u - sr;
  if (!b) { sq = UINT32_MAX; sr = a; }
  check(hart, div == sq && rem == sr && divu == uq && remu == ur && *page == a, 0x20000);
  ++result[hart].reserved[0];
}
void m5_memory_main(uint32_t hart) {
  static const uint32_t edges[] = {0, 1, 2, 3, 0xffff, 0x10000,
    0x7fffffff, 0x80000000, 0x80000001, 0xffffffff, 0xaaaaaaaa, 0x55555555};
  for (uint32_t i = 0; i < 12; ++i)
    for (uint32_t j = 0; j < 12; ++j) arithmetic_pair(hart, edges[i], edges[j]);
  uint32_t random = 0x913754abu ^ hart;
  for (uint32_t i = 0; i < 512; ++i) {
    random ^= random << 13; random ^= random >> 17; random ^= random << 5;
    uint32_t a = random;
    random ^= random << 13; random ^= random >> 17; random ^= random << 5;
    arithmetic_pair(hart, a, random);
  }
  check(hart, result[hart].reserved[0] == 656, 0x40000);
  m5_original_memory_main(hart);
}

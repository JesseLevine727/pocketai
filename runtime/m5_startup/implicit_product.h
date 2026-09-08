#ifndef PA_M5_STARTUP_IMPLICIT_PRODUCT_H
#define PA_M5_STARTUP_IMPLICIT_PRODUCT_H
#include "mul_factor.h"
#include "affine_round.h"
#ifdef PA_STARTUP_SHARED_PRODUCT
static __attribute__((noinline))
#else
static inline
#endif
uint32_t pa_startup_project_multiplier(const pa_tenth_factor *factor,
    double weight, uint32_t adjustment, uint32_t shift) {
  union { double floating; uint64_t bits; } w = {.floating = weight};
  uint32_t high = (uint32_t)(w.bits>>32), encoded = (high>>20)&2047u;
  int sum = (int)factor->exponent+(int)encoded;
  int power = (int32_t)adjustment>>20;
  int right = 2080-sum-power-(int)shift;
  if (!(high>>31) && !factor->sign && encoded && encoded < 2047 &&
      factor->exponent && factor->exponent < 2047 && sum > 1023 && sum < 3068 &&
      right >= 5 && right <= 31) {
    /* Top-34 significands A,B have only two high bits (2 or 3).
     * Their cross products are shifts/adds; only low32*low32 needs MULHU. */
    high = (high&0xfffffu)|0x100000u;
    uint32_t a = (factor->high<<13)|(factor->low>>19);
    uint32_t b = (high<<13)|((uint32_t)w.bits>>19);
    uint32_t abit = (factor->high>>19)&1u, bbit = (high>>19)&1u;
    uint64_t cross = ((uint64_t)a+b)<<1;
    if (abit) cross += b;
    if (bbit) cross += a;
    uint32_t product_high = (uint32_t)(((uint64_t)a*b)>>32);
    uint64_t middle = (uint64_t)product_high+(uint32_t)cross;
    uint32_t hi = 4u+2u*abit+2u*bbit+(abit&bbit)+(uint32_t)(cross>>32)+(uint32_t)(middle>>32);
    uint32_t lo = (uint32_t)middle, r = (uint32_t)right;
    uint32_t q = (lo>>r)|(hi<<(32-r));
    uint32_t remainder = lo&((UINT32_C(1)<<r)-1), half = UINT32_C(1)<<(r-1);
    /* W=floor(A*B/2^32). Full omitted significands contribute <8 word units;
     * floor and binary64 rounding give the conservative [W-1,W+10] enclosure.
     * For r>=5, either test below keeps the WHOLE interval on one side of
     * the nearest halfway boundary, including possible wrap at an integer.
     * Near any halfway, execute the original full two-rounding computation. */
    if (remainder+10u < half) return q;
    if (remainder > half+1u) return q+1;
  }
  w.floating = pa_tenth_mul_factor(factor, weight);
  w.bits += (uint64_t)adjustment<<32;
  return pa_scalar_rne_scaled32(w.bits, shift);
}
#endif

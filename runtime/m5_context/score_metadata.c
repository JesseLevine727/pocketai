#include "score_metadata.h"
#include "pa_m5_numerics.h"
#include "mul_factor.h"
#include "affine_round.h"
#ifdef PA_CONTEXT_SCORE_PRODUCT
#include "score_product.h"
#endif

/* Query-local, exact-key cache. A collision replaces an entry; it can never
 * substitute a different unit. Epochs prevent reuse across query/shift changes. */
typedef struct { uint64_t key; uint32_t epoch, multiplier; } score_entry;
#if defined(PA_CONTEXT_LOCAL_SCORES) && defined(__riscv)
static score_entry entries[128] __attribute__((section(".context_lookup")));
#else
static score_entry entries[128];
#endif
static uint32_t epoch;

static double times32(double value) {
  union { double floating; uint64_t bits; } x = {.floating = value};
  uint32_t exponent = (uint32_t)((x.bits >> 52) & 2047u);
  if (exponent && exponent < 2042) { x.bits += UINT64_C(5) << 52; return x.floating; }
  return value * 32.0;
}

int pa_context_score_metadata(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch) {
  pa_tenth_factor factor = pa_tenth_prepare_factor(query_unit);
  double maximum = times32(pa_tenth_mul_factor(&factor, maximum_unit));
  uint32_t unused, selected;
  if (pa_m5_affine_metadata(&maximum, 1, &unused, &selected)) goto fallback;
  if (++epoch == 0) {
    for (uint32_t i = 0; i < 128; ++i) entries[i].epoch = 0;
    epoch = 1;
  }
  for (uint32_t i = 0; i < length; ++i) {
    union { double floating; uint64_t bits; } unit = {.floating = units[i]}, scale;
    uint32_t low = (uint32_t)unit.bits, high = (uint32_t)(unit.bits >> 32);
    score_entry *entry = entries + ((low ^ (low >> 16) ^ high) & 127u);
    uint32_t multiplier;
    if (entry->epoch == epoch && entry->key == unit.bits) multiplier = entry->multiplier;
    else {
#ifdef PA_CONTEXT_SCORE_PRODUCT
      multiplier = pa_context_score_product(&factor, unit.floating, selected);
      if (multiplier == UINT32_MAX) {
#endif
      scale.floating = times32(pa_tenth_mul_factor(&factor, unit.floating));
      if ((scale.bits >> 63) || ((scale.bits >> 52) & 2047u) == 2047u) goto fallback;
      multiplier = pa_scalar_rne_scaled32(scale.bits, selected);
      if (multiplier >= UINT32_C(0x80000000) || (!multiplier && scale.bits)) goto fallback;
#ifdef PA_CONTEXT_SCORE_PRODUCT
      }
      if (!multiplier || multiplier >= UINT32_C(0x80000000)) goto fallback;
#endif
      entry->key = unit.bits; entry->multiplier = multiplier; entry->epoch = epoch;
    }
    multipliers[i] = multiplier;
  }
  *shift = selected;
  return 0;
fallback:
  for (uint32_t i = 0; i < length; ++i) scratch[i] = query_unit * units[i] * 32.0;
  return pa_m5_affine_metadata(scratch, length, multipliers, shift);
}

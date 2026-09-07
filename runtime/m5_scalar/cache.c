#include "cache.h"

#define DOMAIN 32769u
static uint32_t *cached_multiplier;
static double *cached_unit;
uint32_t pa_scalar_cache_hits, pa_scalar_cache_misses;

void pa_scalar_cache_begin(pa_m5_workspace *workspace) {
  cached_multiplier = 0; cached_unit = 0;
  pa_scalar_cache_hits = 0; pa_scalar_cache_misses = 0;
  /* The fixed full model needs <2 MiB of temporary space for rows<=16.
   * Optional preparation must leave that much untouched. Small standalone
   * workspaces retain their original capacity and arithmetic behavior. */
  if (!workspace || workspace->used > workspace->capacity ||
      workspace->capacity - workspace->used < 3u*1024u*1024u) return;
  uint32_t mark = workspace->used;
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, DOMAIN*4, 64);
  double *units = pa_m5_workspace_allocate(workspace, DOMAIN*8, 64);
  if (!multipliers || !units) {
    pa_m5_workspace_rewind(workspace, mark); return;
  }
  /* Zero means absent; every nonzero maximum in this domain has a nonzero
   * multiplier. Unit memory need not be read or initialized until present. */
  for (uint32_t i = 0; i < DOMAIN; ++i) multipliers[i] = 0;
  cached_unit = units; cached_multiplier = multipliers;
}

void pa_scalar_cache_end(void) {
  cached_multiplier = 0; cached_unit = 0;
}

double pa_scalar_dynamic(uint32_t maximum, uint32_t unit_shift, uint32_t *multiplier) {
  if (!maximum) { *multiplier = 0; return 1.0; }
  double unit;
  if (cached_multiplier && maximum < DOMAIN && cached_multiplier[maximum]) {
    *multiplier = cached_multiplier[maximum];
    unit = cached_unit[maximum];
    ++pa_scalar_cache_hits;
  } else {
    *multiplier = pa_m5_dynamic_multiplier(maximum);
    unit = pa_m5_dynamic_unit(*multiplier, 1.0/256.0);
    ++pa_scalar_cache_misses;
    if (cached_multiplier && maximum < DOMAIN) {
      cached_unit[maximum] = unit;
      cached_multiplier[maximum] = *multiplier;
    }
  }
  /* All callers request Q8 or Q15 units. A nonzero uint32 multiplier gives
   * a normal binary64 value; dividing by 128 changes only its exponent.
   * An all-zero multiplier must retain original sentinel unit 1.0. */
  if (unit_shift == 15 && *multiplier) {
    union { double floating; uint64_t bits; } value = {.floating = unit};
    value.bits -= UINT64_C(7) << 52;
    unit = value.floating;
  }
  return unit;
}

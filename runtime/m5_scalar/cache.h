#ifndef PA_M5_SCALAR_CACHE_H
#define PA_M5_SCALAR_CACHE_H
#include "pa_m5_model.h"
/* Lazy exact table, owned only by hart 0 during one forward chunk. Never
 * model-persistent, externally provisioned, shared with hart 1 or reused after
 * workspace rewind. Standalone operators use the arithmetic fallback. */
void pa_scalar_cache_begin(pa_m5_workspace *workspace);
void pa_scalar_cache_end(void);
double pa_scalar_dynamic(uint32_t maximum, uint32_t unit_shift, uint32_t *multiplier);
extern uint32_t pa_scalar_cache_hits, pa_scalar_cache_misses;
#endif

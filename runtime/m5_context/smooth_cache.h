#ifndef PA_CONTEXT_SMOOTH_CACHE_H
#define PA_CONTEXT_SMOOTH_CACHE_H
#include <stdint.h>
void pa_context_smooth_bind(uint8_t *trace, int enabled);
void pa_context_smooth_reset(void);
const uint32_t *pa_context_smooth_get(const double *source, uint32_t count, uint32_t *shift);
void pa_context_smooth_put(const double *source, uint32_t count, const uint32_t *values, uint32_t shift);
#endif

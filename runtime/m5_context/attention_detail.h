#ifndef PA_M5_CONTEXT_ATTENTION_DETAIL_H
#define PA_M5_CONTEXT_ATTENTION_DETAIL_H
#include <stdint.h>
enum { CTX_APPEND, CTX_QUERY, CTX_QK, CTX_SCORES, CTX_PROBABILITY,
       CTX_VMAX, CTX_VUNITS, CTX_AV, CTX_OUTPUT, CTX_COUNT };
#ifdef PA_CONTEXT_DIAGNOSTIC
uint64_t pa_context_begin(void);
void pa_context_end(uint32_t kind, uint64_t start);
void pa_context_publish(volatile uint32_t *output);
#else
static inline uint64_t pa_context_begin(void) { return 0; }
static inline void pa_context_end(uint32_t kind, uint64_t start) {
  (void)kind; (void)start;
}
static inline void pa_context_publish(volatile uint32_t *output) { (void)output; }
#endif
#endif

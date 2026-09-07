#include "local_scores.h"
#include "quantize.h"
#if defined(__riscv)
static int32_t local[1024] __attribute__((section(".context_scores")));
#else
static int32_t local[1024];
#endif
#ifdef PA_CONTEXT_COMBINED_SCORES
int32_t *pa_context_score_storage(void) { return local; }
#endif
int pa_context_local_scores(const int32_t *raw, const uint32_t *multipliers,
                            uint32_t length, uint32_t shift, int32_t *tagged) {
  int32_t maximum = INT32_MIN;
  for (uint32_t i = 0; i < length; ++i) {
    int64_t value = pa_scalar_rne_product(raw[i], multipliers[i], shift);
    if (value < INT32_MIN || value > INT32_MAX) return -1;
    local[i] = (int32_t)value;
    if (value > maximum) maximum = (int32_t)value;
  }
  for (uint32_t i = 0; i < length; ++i) {
    int64_t difference = (int64_t)local[i]-maximum;
    int16_t score = difference < -32768 ? -32768 : (int16_t)difference;
    tagged[i] = UINT32_C(0x10000) | (uint16_t)score;
  }
  return 0;
}

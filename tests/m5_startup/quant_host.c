#include "bounded_quant.h"
#include "word_affine.h"
void pa_startup_bounded_test(const int32_t *input, const uint32_t *multiplier,
                             int8_t *output, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) output[i] = pa_startup_bounded_quant(input[i], multiplier[i]);
}
void pa_startup_signed_test(const int32_t *input, const uint32_t *multiplier,
                             int8_t *output, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) output[i] = pa_startup_signed_quant(input[i], multiplier[i]);
}
void pa_startup_word_test(const int32_t *input, const uint32_t *multiplier,
    const uint32_t *shift, int32_t *output, int32_t *status, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) {
    uint32_t magnitude = input[i] < 0 ? 0u-(uint32_t)input[i] : (uint32_t)input[i];
    status[i] = startup_word_affine(input[i], magnitude, multiplier[i], shift[i], output+i);
  }
}

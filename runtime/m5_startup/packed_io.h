#ifndef PA_M5_STARTUP_PACKED_IO_H
#define PA_M5_STARTUP_PACKED_IO_H
#include <stdint.h>
typedef uint32_t startup_word __attribute__((__may_alias__));
static void startup_expand(const int16_t *source, int32_t *output, uint32_t count) {
  uint32_t i = 0;
  if (!((uintptr_t)source&3u)) for (; i+1 < count; i += 2) {
    uint32_t word = ((const startup_word *)source)[i/2];
    output[i] = (int16_t)word; output[i+1] = (int16_t)(word>>16);
  }
  for (; i < count; ++i) output[i] = source[i];
}
static void startup_pack(const int32_t *source, int16_t *output, uint32_t count) {
  uint32_t i = 0;
  if (!((uintptr_t)output&3u)) for (; i+1 < count; i += 2)
    ((startup_word *)output)[i/2] = (uint16_t)source[i]|(uint32_t)(uint16_t)source[i+1]<<16;
  for (; i < count; ++i) output[i] = (int16_t)source[i];
}
#endif

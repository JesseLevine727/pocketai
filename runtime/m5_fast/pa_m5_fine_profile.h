#ifndef PA_M5_FINE_PROFILE_H
#define PA_M5_FINE_PROFILE_H
#include <stdint.h>
enum { PA_FAST_DYNAMIC, PA_FAST_NORM_METADATA, PA_FAST_SMOOTH,
       PA_FAST_AFFINE_ROW, PA_FAST_HEAD_AFFINE_ROW, PA_FAST_AFFINE_METADATA,
       PA_FAST_HEAD_AFFINE_METADATA, PA_FAST_PROJECT, PA_FAST_HEAD_PROJECT,
       PA_FAST_PROFILE_COUNT };
extern uint32_t pa_fast_profile_enabled, pa_fast_profile_head;
uint64_t pa_fast_profile_begin(void);
void pa_fast_profile_end(uint32_t kind, uint64_t start);
void pa_fast_profile_publish(volatile uint32_t *destination);
#endif

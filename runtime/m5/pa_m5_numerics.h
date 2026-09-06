#ifndef PA_M5_NUMERICS_H
#define PA_M5_NUMERICS_H
#include <stddef.h>
#include <stdint.h>

#define PA_M5_ARENA_BYTES UINT32_C(0x10000000)
#define PA_M5_ARRAY_COUNT 248u
#define PA_M5_REGION_COUNT 15u

typedef struct {
  const uint8_t *base;
  uint32_t bytes;
  const uint32_t *header;
} pa_m5_arena;

uint64_t pa_m5_rne_u64(uint64_t numerator, uint64_t denominator);
int64_t pa_m5_rne_i64(int64_t numerator, uint64_t denominator);
uint64_t pa_m5_rne_f64(double value);
int64_t pa_m5_rne_f64_signed(double value);
double pa_m5_sqrt_f64(double value);
int16_t pa_m5_sat_i16(int64_t value);
int8_t pa_m5_sat_i8(int64_t value);
uint32_t pa_m5_dynamic_multiplier(uint32_t maximum);
double pa_m5_dynamic_unit(uint32_t multiplier, double input_unit);
int pa_m5_affine_metadata(const double *scales, uint32_t count,
                          uint32_t *multipliers, uint32_t *shift);
uint32_t pa_m5_storage_exponent(double maximum);
int pa_m5_layernorm_metadata(const int16_t *values, uint32_t count,
                             uint32_t exponent, const double *gain,
                             const double *bias, int16_t *gain_q12,
                             int32_t *bias_q8, uint32_t *factor);
int pa_m5_arena_open(pa_m5_arena *arena, const void *bytes, uint32_t length);
const void *pa_m5_arena_array(const pa_m5_arena *arena, uint32_t id,
                              uint32_t *payload_bytes);
#endif

#ifndef PA_M5_CONTEXT_READY_CACHE_H
#define PA_M5_CONTEXT_READY_CACHE_H
#include "pa_m5_ops.h"

#define PA_CONTEXT_WORK_LIMIT UINT32_C(0x280000)
#define PA_CONTEXT_META_OFFSET UINT32_C(0x60000)
#define PA_CONTEXT_VALUE_OFFSET UINT32_C(0x80000)
#define PA_CONTEXT_MAGIC UINT32_C(0x36564350)
typedef struct {
  uint32_t magic, version;
  uint32_t valid[144];
  double key_maximum_unit[144];
  uint16_t maximum[144][64];
  uint32_t multiplier[144][64];
  double unit[144][64];
  uint32_t cold_heads, updated_columns, appended_vectors, reserved;
} pa_context_state;
_Static_assert(sizeof(pa_context_state) <= 0x20000, "derived metadata overlaps V cache");

/* Bind only pointers: all initialization/maintenance occurs inside attention. */
void pa_context_bind(pa_m5_cache *cache, uint8_t *work, uint8_t *trace, int enabled);
int pa_context_enabled(const pa_m5_cache *cache);
int pa_context_prepare(pa_m5_cache *cache, uint32_t layer, uint32_t past);
void pa_context_store_key(pa_m5_cache *cache, uint32_t layer, uint32_t head,
                           uint32_t position, uint32_t feature, int8_t value);
const int8_t *pa_context_key_tile(pa_m5_cache *cache, uint32_t layer,
                                  uint32_t head, uint32_t tile);
int pa_context_update_values(pa_m5_cache *cache, uint32_t layer, uint32_t head,
                               uint32_t position);
const int8_t *pa_context_value_tile(uint32_t layer, uint32_t head, uint32_t tile);
const double *pa_context_value_units(uint32_t layer, uint32_t head);
double pa_context_key_maximum(uint32_t layer, uint32_t head);
#endif

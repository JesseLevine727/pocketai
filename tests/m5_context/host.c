#include "ready_cache.h"
void pa_context_host_bind(int16_t *keys, int16_t *values, int8_t *keys_i8,
                           double *key_units, uint8_t *work, uint8_t *trace, int enabled) {
  pa_m5_cache cache = {keys, values, keys_i8, key_units};
  pa_context_bind(&cache, work, trace, enabled);
}
uint32_t pa_context_host_state_bytes(void) { return sizeof(pa_context_state); }

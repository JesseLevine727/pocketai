#include "smooth_cache.h"
typedef struct { uint64_t key; uint32_t count, offset, shift, reserved; } entry;
typedef struct { uint32_t magic, count, used, reserved; entry entries[24]; } metadata;
static metadata *meta;
static uint32_t *storage;
#define MAGIC UINT32_C(0x36534d43)
void pa_context_smooth_bind(uint8_t *trace, int enabled) {
  meta = enabled ? (metadata *)(trace+0x5d000) : 0;
  storage = enabled ? (uint32_t *)(trace+0x30000) : 0;
}
void pa_context_smooth_reset(void) {
  if (!meta) return;
  meta->magic = MAGIC; meta->count = 0; meta->used = 0; meta->reserved = 0;
}
const uint32_t *pa_context_smooth_get(const double *source, uint32_t count, uint32_t *shift) {
  if (!meta || meta->magic != MAGIC || meta->count > 24 || meta->used > 46080) return 0;
  for (uint32_t i = 0; i < meta->count; ++i) {
    const entry *item = meta->entries+i;
    if (item->key == (uint64_t)(uintptr_t)source && item->count == count) {
      *shift = item->shift; return storage+item->offset;
    }
  }
  return 0;
}
void pa_context_smooth_put(const double *source, uint32_t count, const uint32_t *values, uint32_t shift) {
  if (!meta || meta->magic != MAGIC || meta->count >= 24 || meta->used > 46080 || count > 46080-meta->used) return;
  uint32_t used = meta->used;
  for (uint32_t i = 0; i < count; ++i) storage[used+i] = values[i];
  entry *item = meta->entries+meta->count;
  item->key = (uint64_t)(uintptr_t)source; item->count = count;
  item->offset = used; item->shift = shift; item->reserved = 0;
  meta->used += count; ++meta->count;
}

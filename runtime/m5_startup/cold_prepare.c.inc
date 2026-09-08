/* Cold phases may borrow local-score BRAM: no attention score is live yet.
 * Each hart owns disjoint scratch and output ranges, joined between phases. */
#include "local_scores.h"
typedef struct { int8_t *keys; uint32_t past; } startup_transpose_job;
static void startup_transpose(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  startup_transpose_job *job = opaque;
  uint32_t *temporary = (uint32_t *)pa_context_score_storage()+worker*256;
  for (uint32_t block = first; block < end; ++block) {
    word_alias *tile = (word_alias *)(job->keys+block*1024);
    for (uint32_t i = 0; i < 256; ++i) temporary[i] = tile[i];
    for (uint32_t feature = 0; feature < 64; feature += 4)
      for (uint32_t column = 0; column < 16; column += 4) {
        uint32_t position = block*16+column;
        uint32_t a = position < job->past ? temporary[column*16+feature/4] : 0;
        uint32_t b = position+1 < job->past ? temporary[(column+1)*16+feature/4] : 0;
        uint32_t c = position+2 < job->past ? temporary[(column+2)*16+feature/4] : 0;
        uint32_t d = position+3 < job->past ? temporary[(column+3)*16+feature/4] : 0;
        uint32_t x = (a&0x00ff00ffu)|((b&0x00ff00ffu)<<8);
        uint32_t y = ((a>>8)&0x00ff00ffu)|(b&0xff00ff00u);
        uint32_t z = (c&0x00ff00ffu)|((d&0x00ff00ffu)<<8);
        uint32_t w = ((c>>8)&0x00ff00ffu)|(d&0xff00ff00u);
        tile[feature*4+column/4] = (x&0xffffu)|(z<<16);
        tile[(feature+1)*4+column/4] = (y&0xffffu)|(w<<16);
        tile[(feature+2)*4+column/4] = (x>>16)|(z&0xffff0000u);
        tile[(feature+3)*4+column/4] = (y>>16)|(w&0xffff0000u);
      }
  }
}
typedef struct {
  const int16_t *values;
  const double *units;
  uint32_t *maximum[2];
  double key_maximum[2];
} startup_scan_job;
static void startup_scan(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  startup_scan_job *job = opaque;
  uint32_t *maximum = job->maximum[worker];
  for (uint32_t i = 0; i < 64; ++i) maximum[i] = 0;
  double key_maximum = 0;
  for (uint32_t position = first; position < end; ++position) {
    const word_alias *vector = (const word_alias *)(job->values+position*64);
    for (uint32_t pair = 0; pair < 32; ++pair) {
      uint32_t packed = vector[pair];
      uint32_t a = magnitude((int16_t)packed), b = magnitude((int16_t)(packed >> 16));
      if (a > maximum[pair*2]) maximum[pair*2] = a;
      if (b > maximum[pair*2+1]) maximum[pair*2+1] = b;
    }
    double unit = job->units[position];
    if (unit > key_maximum) key_maximum = unit;
  }
  job->key_maximum[worker] = key_maximum;
}

int pa_context_prepare(pa_m5_cache *cache, uint32_t layer, uint32_t past) {
  if (!pa_context_enabled(cache) || layer >= 12 || past > 1023) return -1;
  uint64_t prepare_total = pa_startup_begin();
  if ((layer == 0 && past == 0) || state->magic != PA_CONTEXT_MAGIC || state->version != 1) {
    pa_context_smooth_reset();
    state->magic = PA_CONTEXT_MAGIC; state->version = 1;
    state->cold_heads = 0; state->updated_columns = 0; state->appended_vectors = 0;
    state->reserved = 0;
    for (uint32_t i = 0; i < 144; ++i) state->valid[i] = UINT32_MAX;
  }
  for (uint32_t head = 0; head < 12; ++head) {
    uint32_t index = layer*12+head;
    if (state->valid[index] != UINT32_MAX) {
      if (state->valid[index] != past) return -2;
      continue;
    }
    uint64_t total = pa_startup_begin(), stamp = total;
    startup_transpose_job transpose = {cache->keys_i8+index*65536u, past};
    if (pa_context_parallel(startup_transpose, &transpose, (past+15)/16)) return -40;
    pa_startup_end(START_TRANSPOSE, stamp); stamp = pa_startup_begin();
    const int16_t *values = cache->values+index*65536u;
    startup_scan_job scan;
    scan.values = values; scan.units = cache->key_units+index*1024u;
    scan.maximum[0] = (uint32_t *)pa_context_score_storage();
    scan.maximum[1] = scan.maximum[0]+64;
    /* The second worker is unused for short prefixes; initialize its reduction. */
    for (uint32_t i = 0; i < 64; ++i) scan.maximum[1][i] = 0;
    scan.key_maximum[0] = 0; scan.key_maximum[1] = 0;
    if (pa_context_parallel(startup_scan, &scan, past)) return -40;
    pa_startup_end(START_SCAN, stamp); stamp = pa_startup_begin();
    state->key_maximum_unit[index] = scan.key_maximum[0] > scan.key_maximum[1] ? scan.key_maximum[0] : scan.key_maximum[1];
    uint32_t multiplier[64];
    for (uint32_t feature = 0; feature < 64; ++feature) {
      uint32_t a = scan.maximum[0][feature], b = scan.maximum[1][feature];
      uint32_t maximum = a > b ? a : b;
      state->maximum[index][feature] = (uint16_t)maximum;
      state->unit[index][feature] = pa_scalar_dynamic(maximum, 8, multiplier+feature);
      if (multiplier[feature] == UINT32_MAX) return -3;
      state->multiplier[index][feature] = multiplier[feature];
    }
    pa_startup_end(START_UNITS, stamp); stamp = pa_startup_begin();
    if (past) {
      value_job job = {values, values, value_head(index), multiplier, 0xffffu,
                       past-1, {UINT32_MAX, UINT32_MAX}};
      if (pa_context_parallel(update_groups, &job, past)) return -40;
    }
    pa_startup_end(START_VALUES, stamp); pa_startup_end(START_INIT_TOTAL, total);
    state->valid[index] = past;
    ++state->cold_heads;
  }
  pa_startup_end(START_PREPARE_TOTAL, prepare_total);
  return 0;
}

#include "ready_cache.h"
#include "cache.h"
#include "quantize.h"
#ifdef PA_CONTEXT_SMOOTH_CACHE
#include "smooth_cache.h"
#endif
#ifdef PA_CONTEXT_PARALLEL_VALUES
#include "parallel.h"
#endif

typedef uint32_t word_alias __attribute__((__may_alias__));
static const int16_t *bound_keys, *bound_values;
static const int8_t *bound_i8;
static uint8_t *value_first, *value_rest;
static pa_context_state *state;
static int enabled;

void pa_context_bind(pa_m5_cache *cache, uint8_t *work, uint8_t *trace, int active) {
  enabled = active && cache && work && trace;
  bound_keys = enabled ? cache->keys : 0;
  bound_values = enabled ? cache->values : 0;
  bound_i8 = enabled ? cache->keys_i8 : 0;
  value_first = enabled ? work + PA_CONTEXT_WORK_LIMIT : 0;
  value_rest = enabled ? trace + PA_CONTEXT_VALUE_OFFSET : 0;
  state = enabled ? (pa_context_state *)(trace + PA_CONTEXT_META_OFFSET) : 0;
#ifdef PA_CONTEXT_SMOOTH_CACHE
  pa_context_smooth_bind(trace, enabled);
#endif
}

int pa_context_enabled(const pa_m5_cache *cache) {
  return enabled && cache && cache->keys == bound_keys && cache->values == bound_values &&
         cache->keys_i8 == bound_i8;
}

static int8_t *value_head(uint32_t index) {
  return (int8_t *)(index < 24 ? value_first + index*65536u : value_rest + (index-24)*65536u);
}

static uint32_t magnitude(int16_t value) {
  return value < 0 ? (uint32_t)-(int32_t)value : (uint32_t)value;
}

static void transpose_keys(int8_t *keys, uint32_t past) {
  /* One local 1024-byte tile. Every DDR load/store is a complete word. */
  uint32_t temporary[256];
  for (uint32_t block = 0; block < (past+15)/16; ++block) {
    word_alias *tile = (word_alias *)(keys + block*1024);
    for (uint32_t i = 0; i < 256; ++i) temporary[i] = tile[i];
    const uint8_t *bytes = (const uint8_t *)temporary;
    for (uint32_t feature = 0; feature < 64; ++feature)
      for (uint32_t column = 0; column < 16; column += 4) {
        uint32_t packed = 0;
        for (uint32_t lane = 0; lane < 4; ++lane)
          if (block*16+column+lane < past)
            packed |= (uint32_t)bytes[(column+lane)*64+feature] << (lane*8);
        tile[feature*4+column/4] = packed;
      }
  }
}

static uint32_t quantized_four(const int16_t *source, const uint32_t *multiplier) {
  uint32_t a = ((const word_alias *)source)[0];
  uint32_t b = ((const word_alias *)source)[1];
  return (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)a, multiplier[0]) |
         (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)(a >> 16), multiplier[1]) << 8 |
         (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)b, multiplier[2]) << 16 |
         (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)(b >> 16), multiplier[3]) << 24;
}
#ifdef PA_CONTEXT_MASKED_VALUES
static uint32_t quantized_changed(const int16_t *source, const uint32_t *multiplier,
                                  uint32_t packed, uint32_t mask) {
  uint32_t a = 0, b = 0;
  if (mask & 3u) a = ((const word_alias *)source)[0];
  if (mask & 12u) b = ((const word_alias *)source)[1];
  if (mask & 1u) packed = (packed & UINT32_C(0xffffff00)) |
      (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)a, multiplier[0]);
  if (mask & 2u) packed = (packed & UINT32_C(0xffff00ff)) |
      (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)(a >> 16), multiplier[1]) << 8;
  if (mask & 4u) packed = (packed & UINT32_C(0xff00ffff)) |
      (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)b, multiplier[2]) << 16;
  if (mask & 8u) packed = (packed & UINT32_C(0x00ffffff)) |
      (uint32_t)(uint8_t)pa_scalar_quantize24((int16_t)(b >> 16), multiplier[3]) << 24;
  return packed;
}
#endif

static void rebuild_group(const int16_t *values, int8_t *ready, uint32_t feature,
                            uint32_t length, const uint32_t *multiplier) {
  word_alias *output = (word_alias *)(ready + (feature/16)*16384 + (feature%16));
  for (uint32_t position = 0; position < length; ++position)
    output[position*4] = quantized_four(values + position*64 + feature, multiplier);
}

#ifdef PA_CONTEXT_PARALLEL_VALUES
typedef struct {
  const int16_t *values, *input;
  int8_t *ready;
  const uint32_t *multipliers;
  uint32_t changed, position;
#ifdef PA_CONTEXT_MASKED_VALUES
  uint32_t features[2];
#endif
} value_job;
static void update_groups(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  value_job *job = opaque; (void)worker;
#ifdef PA_CONTEXT_POSITION_VALUES
  /* Partition positions, not feature groups: even a single changed group
   * then uses both harts. Each worker writes disjoint complete words. */
  for (uint32_t feature = 0; feature < 64; feature += 4) {
#ifdef PA_CONTEXT_MASKED_VALUES
    uint32_t mask = (job->features[feature/32] >> (feature%32)) & 15u;
    word_alias *output = (word_alias *)(job->ready+(feature/16)*16384+feature%16);
    if (mask == 15) {
      for (uint32_t position = first; position < end; ++position)
        output[position*4] = quantized_four(job->values+position*64+feature, job->multipliers+feature);
      continue;
    }
    if (mask) {
      uint32_t limit = end < job->position ? end : job->position;
      for (uint32_t position = first; position < limit; ++position)
        output[position*4] = quantized_changed(job->values+position*64+feature,
            job->multipliers+feature, output[position*4], mask);
    }
    if (job->position >= first && job->position < end)
      output[job->position*4] = quantized_four(job->input+feature, job->multipliers+feature);
#else
    if (job->changed & (1u << (feature/4))) {
      word_alias *output = (word_alias *)(job->ready+(feature/16)*16384+feature%16);
      for (uint32_t position = first; position < end; ++position)
        output[position*4] = quantized_four(job->values+position*64+feature, job->multipliers+feature);
    } else if (job->position >= first && job->position < end) {
      word_alias *destination = (word_alias *)(job->ready+(feature/16)*16384+job->position*16+feature%16);
      *destination = quantized_four(job->input+feature, job->multipliers+feature);
    }
#endif
  }
#else
  for (uint32_t feature = first; feature < end; feature += 4) {
    if (job->changed & (1u << (feature/4)))
      rebuild_group(job->values, job->ready, feature, job->position+1, job->multipliers+feature);
    else {
      word_alias *destination = (word_alias *)(job->ready + (feature/16)*16384 + job->position*16 + feature%16);
      *destination = quantized_four(job->input+feature, job->multipliers+feature);
    }
  }
#endif
}
#endif

int pa_context_prepare(pa_m5_cache *cache, uint32_t layer, uint32_t past) {
  if (!pa_context_enabled(cache) || layer >= 12 || past > 1023) return -1;
  if ((layer == 0 && past == 0) || state->magic != PA_CONTEXT_MAGIC || state->version != 1) {
#ifdef PA_CONTEXT_SMOOTH_CACHE
    pa_context_smooth_reset();
#endif
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
    uint32_t maximum[64], multiplier[64];
    for (uint32_t feature = 0; feature < 64; ++feature) maximum[feature] = 0;
    const int16_t *values = cache->values + index*65536u;
    transpose_keys(cache->keys_i8 + index*65536u, past);
    double maximum_unit = 0;
    for (uint32_t position = 0; position < past; ++position) {
      const word_alias *vector = (const word_alias *)(values + position*64);
      for (uint32_t pair = 0; pair < 32; ++pair) {
        uint32_t packed = vector[pair];
        uint32_t a = magnitude((int16_t)packed), b = magnitude((int16_t)(packed >> 16));
        if (a > maximum[pair*2]) maximum[pair*2] = a;
        if (b > maximum[pair*2+1]) maximum[pair*2+1] = b;
      }
      double unit = cache->key_units[index*1024u+position];
      if (unit > maximum_unit) maximum_unit = unit;
    }
    state->key_maximum_unit[index] = maximum_unit;
    for (uint32_t feature = 0; feature < 64; ++feature) {
      state->maximum[index][feature] = (uint16_t)maximum[feature];
      state->unit[index][feature] = pa_scalar_dynamic(maximum[feature], 8, multiplier+feature);
      if (multiplier[feature] == UINT32_MAX) return -3;
      state->multiplier[index][feature] = multiplier[feature];
    }
    for (uint32_t feature = 0; feature < 64; feature += 4)
      rebuild_group(values, value_head(index), feature, past, multiplier+feature);
    state->valid[index] = past;
    ++state->cold_heads;
  }
  return 0;
}

void pa_context_store_key(pa_m5_cache *cache, uint32_t layer, uint32_t head,
                           uint32_t position, uint32_t feature, int8_t value) {
  cache->keys_i8[(layer*12+head)*65536u + (position/16)*1024 + feature*16 + position%16] = value;
}

const int8_t *pa_context_key_tile(pa_m5_cache *cache, uint32_t layer,
                                  uint32_t head, uint32_t tile) {
  return cache->keys_i8 + (layer*12+head)*65536u + tile*1024;
}

int pa_context_update_values(pa_m5_cache *cache, uint32_t layer, uint32_t head,
                               uint32_t position) {
  uint32_t index = layer*12+head;
  if (state->valid[index] != position) return -1;
  const int16_t *values = cache->values + index*65536u;
  const int16_t *input = values + position*64;
  int8_t *ready = value_head(index);
  uint32_t multiplier[64], changed = 0;
#ifdef PA_CONTEXT_MASKED_VALUES
  uint32_t features[2] = {0, 0};
#endif
  for (uint32_t feature = 0; feature < 64; ++feature) {
    uint32_t maximum = magnitude(input[feature]);
    if (maximum > state->maximum[index][feature]) {
      state->maximum[index][feature] = (uint16_t)maximum;
      state->unit[index][feature] = pa_scalar_dynamic(maximum, 8, multiplier+feature);
      if (multiplier[feature] == UINT32_MAX) return -2;
      state->multiplier[index][feature] = multiplier[feature];
      changed |= 1u << (feature/4);
#ifdef PA_CONTEXT_MASKED_VALUES
      features[feature/32] |= 1u << (feature%32);
#endif
      ++state->updated_columns;
    } else multiplier[feature] = state->multiplier[index][feature];
  }
#ifdef PA_CONTEXT_PARALLEL_VALUES
#ifdef PA_CONTEXT_MASKED_VALUES
  value_job job = {values, input, ready, multiplier, changed, position, {features[0], features[1]}};
#else
  value_job job = {values, input, ready, multiplier, changed, position};
#endif
#ifdef PA_CONTEXT_POSITION_VALUES
  if (pa_context_parallel(update_groups, &job, position+1)) return -40;
#else
  if (pa_context_parallel(update_groups, &job, 64)) return -40;
#endif
#else
  for (uint32_t feature = 0; feature < 64; feature += 4) {
    if (changed & (1u << (feature/4)))
      rebuild_group(values, ready, feature, position+1, multiplier+feature);
    else {
      word_alias *destination = (word_alias *)(ready + (feature/16)*16384 + position*16 + feature%16);
      *destination = quantized_four(input+feature, multiplier+feature);
    }
  }
#endif
  double unit = cache->key_units[index*1024u+position];
  if (unit > state->key_maximum_unit[index]) state->key_maximum_unit[index] = unit;
  state->valid[index] = position+1;
  ++state->appended_vectors;
  return 0;
}

const int8_t *pa_context_value_tile(uint32_t layer, uint32_t head, uint32_t tile) {
  return value_head(layer*12+head) + tile*16384;
}
const double *pa_context_value_units(uint32_t layer, uint32_t head) {
  return state->unit[layer*12+head];
}
double pa_context_key_maximum(uint32_t layer, uint32_t head) {
  return state->key_maximum_unit[layer*12+head];
}

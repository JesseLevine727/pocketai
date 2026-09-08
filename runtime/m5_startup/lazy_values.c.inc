/* Quantized zero probabilities annihilate V exactly. Maintain full-prefix
 * maxima/units, but materialize only demanded rows at the CURRENT maxima.
 * A published bit certifies all 64 features; any maximum change clears it. */
typedef struct {
  const int16_t *values;
  const uint32_t *multipliers;
  int8_t *ready;
  const uint16_t *positions;
  uint32_t count;
} startup_lazy_job;
static void startup_lazy_convert(void *opaque, uint32_t first,
                                  uint32_t end, uint32_t worker) {
  const startup_lazy_job *job = opaque; (void)worker;
  for (uint32_t feature = first; feature < end; feature += 4) {
    const uint32_t m0 = job->multipliers[feature], m1 = job->multipliers[feature+1];
    const uint32_t m2 = job->multipliers[feature+2], m3 = job->multipliers[feature+3];
    const int16_t *values = job->values+feature;
    word_alias *output = (word_alias *)(job->ready+(feature/16)*16384+feature%16);
    for (uint32_t i = 0; i < job->count; ++i) {
      uint32_t position = job->positions[i];
      const word_alias *input = (const word_alias *)(values+position*64);
      uint32_t a = input[0], b = input[1];
      output[position*4] = (uint8_t)pa_startup_signed_quant((int16_t)a, m0) |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(a>>16), m1) << 8 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)b, m2) << 16 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(b>>16), m3) << 24;
    }
  }
}

int pa_startup_require_values(pa_m5_cache *cache, uint32_t layer, uint32_t head,
                              uint32_t length, const int8_t *probability) {
  if (!pa_context_enabled(cache) || layer >= 12 || head >= 12 ||
      !length || length > 1024 || !probability) return -1;
  uint32_t index = layer*12+head;
  if (state->valid[index] != length) return -2;
  uint64_t stamp = pa_startup_begin();
  /* Scores have been consumed by softmax before this function. This storage
   * is dead until the next query/head; probabilities remain in DDR. */
  uint16_t *positions = (uint16_t *)pa_context_score_storage();
  uint32_t *snapshot = (uint32_t *)(positions+1024);
  uint32_t *bitmap = startup_materialized+index*32;
  for (uint32_t i = 0; i < 32; ++i) snapshot[i] = bitmap[i];
  uint32_t count = 0;
  for (uint32_t position = 0; position < length; ++position) {
    uint32_t mask = 1u << (position&31);
    if (probability[position] && !(snapshot[position/32]&mask)) {
      positions[count++] = (uint16_t)position;
      snapshot[position/32] |= mask;
    }
  }
  if (count) {
    startup_lazy_job job = {cache->values+index*65536u, state->multiplier[index],
                            value_head(index), positions, count};
    if (pa_context_parallel(startup_lazy_convert, &job, 64)) return -40;
    /* Join before publishing: neither hart advertises partially written rows. */
    for (uint32_t i = 0; i < 32; ++i) bitmap[i] = snapshot[i];
  }
  if (startup_initial_pending[index]) {
    startup_initial_pending[index] = 0;
    pa_startup_end(START_LAZY_INITIAL, stamp);
  }
  pa_startup_end(START_LAZY_VALUES, stamp);
  return 0;
}

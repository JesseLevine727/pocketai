/* No changed-feature dispatch in a genuinely cold full conversion. Four
 * maximum-derived multipliers stay in registers for all owned positions. */
static void startup_register_values(void *opaque, uint32_t first,
                                     uint32_t end, uint32_t worker) {
  const value_job *job = opaque; (void)worker;
  const int16_t *values = job->values;
  int8_t *ready = job->ready;
  const uint32_t *multipliers = job->multipliers;
  for (uint32_t feature = 0; feature < 64; feature += 4) {
    const uint32_t m0 = multipliers[feature], m1 = multipliers[feature+1];
    const uint32_t m2 = multipliers[feature+2], m3 = multipliers[feature+3];
    const word_alias *input = (const word_alias *)(values+first*64+feature);
    word_alias *output = (word_alias *)(ready+(feature/16)*16384+feature%16+first*16);
    for (uint32_t position = first; position < end; ++position, input += 32, output += 4) {
      uint32_t a = input[0], b = input[1];
      *output = (uint8_t)pa_startup_signed_quant((int16_t)a, m0) |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(a>>16), m1) << 8 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)b, m2) << 16 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(b>>16), m3) << 24;
    }
  }
}

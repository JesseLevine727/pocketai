/* Exact hot-magnitude table. Store abs(quantize(-m)), not quantize(+m):
 * negative saturation may reach 128 whereas positive saturation ends at 127.
 * Every out-of-table value uses the original full-width scalar operation. */
static void startup_fill_lut(uint32_t *table, const uint32_t *multiplier) {
  for (uint32_t i = 0; i < 256; ++i) {
    int32_t value = -(int32_t)i;
    table[i] = (uint32_t)-(int32_t)pa_scalar_quantize24(value, multiplier[0]) |
        (uint32_t)-(int32_t)pa_scalar_quantize24(value, multiplier[1]) << 8 |
        (uint32_t)-(int32_t)pa_scalar_quantize24(value, multiplier[2]) << 16 |
        (uint32_t)-(int32_t)pa_scalar_quantize24(value, multiplier[3]) << 24;
  }
}
static uint32_t startup_lookup(int16_t value, const uint32_t *table, uint32_t lane,
                                uint32_t multiplier) {
  uint32_t absolute = magnitude(value);
  if (absolute >= 256) return (uint8_t)pa_scalar_quantize24(value, multiplier);
  uint32_t quantized = (table[absolute] >> (lane*8)) & 255u;
  if (value < 0) return (uint8_t)(0u-quantized);
  return quantized > 127 ? 127 : quantized;
}
static void startup_lut_values(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  value_job *job = opaque;
  uint32_t *table = (uint32_t *)pa_context_score_storage()+worker*256;
  for (uint32_t feature = 0; feature < 64; feature += 4) {
    const uint32_t *multiplier = job->multipliers+feature;
    startup_fill_lut(table, multiplier);
    word_alias *output = (word_alias *)(job->ready+(feature/16)*16384+feature%16);
    for (uint32_t position = first; position < end; ++position) {
      const word_alias *source = (const word_alias *)(job->values+position*64+feature);
      uint32_t a = source[0], b = source[1];
      output[position*4] = startup_lookup((int16_t)a, table, 0, multiplier[0]) |
          startup_lookup((int16_t)(a>>16), table, 1, multiplier[1]) << 8 |
          startup_lookup((int16_t)b, table, 2, multiplier[2]) << 16 |
          startup_lookup((int16_t)(b>>16), table, 3, multiplier[3]) << 24;
    }
  }
}
#ifndef __riscv
/* Test-only entry, absent from all deployed images. */
void pa_startup_lut_test(const int16_t *values, const uint32_t *multipliers, int8_t *output) {
  value_job job = {values, values, output, multipliers, 0xffffu, 1023,
                   {UINT32_MAX, UINT32_MAX}};
  startup_lut_values(&job, 0, 512, 0);
  startup_lut_values(&job, 512, 1024, 1);
}
#endif

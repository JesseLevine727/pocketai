/* Track signed extrema, deferring absolute value until after the scan.
 * max(abs(x)) == max(-min(x), max(x)), including -32768. */
static void startup_scan(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  startup_scan_job *job = opaque;
  uint32_t *maximum = job->maximum[worker];
  const int16_t *values = job->values;
  for (uint32_t feature = 0; feature < 64; feature += 4) {
    int32_t lo0 = 0, lo1 = 0, lo2 = 0, lo3 = 0;
    int32_t hi0 = 0, hi1 = 0, hi2 = 0, hi3 = 0;
    const word_alias *input = (const word_alias *)(values+first*64+feature);
    for (uint32_t p = first; p < end; ++p, input += 32) {
      uint32_t a = input[0], b = input[1];
      int32_t v0 = (int16_t)a, v1 = (int16_t)(a>>16);
      int32_t v2 = (int16_t)b, v3 = (int16_t)(b>>16);
      if (v0 < lo0) lo0 = v0;
      if (v1 < lo1) lo1 = v1;
      if (v2 < lo2) lo2 = v2;
      if (v3 < lo3) lo3 = v3;
      if (v0 > hi0) hi0 = v0;
      if (v1 > hi1) hi1 = v1;
      if (v2 > hi2) hi2 = v2;
      if (v3 > hi3) hi3 = v3;
    }
    maximum[feature] = (uint32_t)(-lo0 > hi0 ? -lo0 : hi0);
    maximum[feature+1] = (uint32_t)(-lo1 > hi1 ? -lo1 : hi1);
    maximum[feature+2] = (uint32_t)(-lo2 > hi2 ? -lo2 : hi2);
    maximum[feature+3] = (uint32_t)(-lo3 > hi3 ? -lo3 : hi3);
  }
  union { uint64_t bits; double floating; } maximum_unit = {.bits = 0};
  for (uint32_t p = first; p < end; ++p) {
    union { double floating; uint64_t bits; } unit = {.floating = job->units[p]};
    /* Starting at +0: negative values/zeros and all NaNs never increase max;
     * positive finite values and +infinity have the same integer ordering. */
    if (unit.bits <= UINT64_C(0x7ff0000000000000) && unit.bits > maximum_unit.bits)
      maximum_unit.bits = unit.bits;
  }
  job->key_maximum[worker] = maximum_unit.floating;
}

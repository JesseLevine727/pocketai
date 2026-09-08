/* Keep four maxima in registers across the prefix instead of reading local
 * scratch for every feature of every position. Each input load remains packed. */
static void startup_scan(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  startup_scan_job *job = opaque;
  uint32_t *maximum = job->maximum[worker];
  for (uint32_t feature = 0; feature < 64; feature += 4) {
    uint32_t m0 = 0, m1 = 0, m2 = 0, m3 = 0;
    for (uint32_t position = first; position < end; ++position) {
      const word_alias *source = (const word_alias *)(job->values+position*64+feature);
      uint32_t a = source[0], b = source[1];
      uint32_t v0 = magnitude((int16_t)a), v1 = magnitude((int16_t)(a>>16));
      uint32_t v2 = magnitude((int16_t)b), v3 = magnitude((int16_t)(b>>16));
      if (v0 > m0) m0 = v0;
      if (v1 > m1) m1 = v1;
      if (v2 > m2) m2 = v2;
      if (v3 > m3) m3 = v3;
    }
    maximum[feature] = m0; maximum[feature+1] = m1;
    maximum[feature+2] = m2; maximum[feature+3] = m3;
  }
  double key_maximum = 0;
  for (uint32_t position = first; position < end; ++position) {
    double unit = job->units[position];
    if (unit > key_maximum) key_maximum = unit;
  }
  job->key_maximum[worker] = key_maximum;
}


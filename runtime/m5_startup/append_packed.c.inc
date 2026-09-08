/* Raw K/V publish complete words. Four token positions share one transposed
 * key word; aligned quartets are written once without byte RMW traffic. */
static int startup_append_head(pa_m5_cache *cache, uint32_t layer, uint32_t head,
    uint32_t past, uint32_t rows, const int16_t *qkv) {
  uint32_t multipliers[16];
  uint32_t index = layer*12+head;
  for (uint32_t row = 0; row < rows; ++row) {
    const int16_t *source16 = qkv+row*2304+head*64;
    const startup_word *source = (const startup_word *)source16;
    uint32_t offset = index*65536u+(past+row)*64;
    startup_word *keys = (startup_word *)(cache->keys+offset);
    startup_word *values = (startup_word *)(cache->values+offset);
    uint32_t maximum = 0;
    for (uint32_t pair = 0; pair < 32; ++pair) {
      uint32_t k, v;
      if ((uintptr_t)source16&3u) {
        k = (uint16_t)source16[768+pair*2]|(uint32_t)(uint16_t)source16[769+pair*2]<<16;
        v = (uint16_t)source16[1536+pair*2]|(uint32_t)(uint16_t)source16[1537+pair*2]<<16;
      } else { k = source[384+pair]; v = source[768+pair]; }
      keys[pair] = k; values[pair] = v;
      int32_t a = (int16_t)k, b = (int16_t)(k>>16);
      uint32_t aa = a < 0 ? (uint32_t)-a : (uint32_t)a;
      uint32_t ab = b < 0 ? (uint32_t)-b : (uint32_t)b;
      if (aa > maximum) maximum = aa;
      if (ab > maximum) maximum = ab;
    }
    cache->key_units[index*1024+past+row] = pa_scalar_dynamic(maximum, 8, multipliers+row);
    if (multipliers[row] == UINT32_MAX) return -3;
  }
  for (uint32_t feature = 0; feature < 64; ++feature) {
    const int16_t *input = qkv+head*64+768+feature;
    uint32_t row = 0;
    for (; row < rows && ((past+row)&3u); ++row)
      pa_context_store_key(cache, layer, head, past+row, feature,
          pa_startup_signed_quant(input[row*2304], multipliers[row]));
    for (; row+3 < rows; row += 4) {
      uint32_t position = past+row;
      startup_word *output = (startup_word *)(cache->keys_i8+index*65536u+
          (position/16)*1024+feature*16+position%16);
      *output = (uint8_t)pa_startup_signed_quant(input[row*2304], multipliers[row]) |
          (uint32_t)(uint8_t)pa_startup_signed_quant(input[(row+1)*2304], multipliers[row+1])<<8 |
          (uint32_t)(uint8_t)pa_startup_signed_quant(input[(row+2)*2304], multipliers[row+2])<<16 |
          (uint32_t)(uint8_t)pa_startup_signed_quant(input[(row+3)*2304], multipliers[row+3])<<24;
    }
    for (; row < rows; ++row)
      pa_context_store_key(cache, layer, head, past+row, feature,
          pa_startup_signed_quant(input[row*2304], multipliers[row]));
  }
  return 0;
}

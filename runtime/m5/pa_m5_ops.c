#include "pa_m5_ops.h"

static uint32_t magnitude_i16(int16_t value) {
  return value < 0 ? (uint32_t)-(int32_t)value : (uint32_t)value;
}
static double power2(uint32_t exponent) {
  union { uint64_t bits; double floating; } value = {
      .bits = (uint64_t)(exponent + 1023) << 52};
  return value.floating;
}
static int affine_row(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                      const int32_t *input, const double *scales,
                      const double *bias, uint32_t count, uint32_t operation,
                      int16_t *output) {
  uint32_t mark = workspace->used;
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, count * 4, 64);
  int32_t *bias_q = pa_m5_workspace_allocate(workspace, count * 4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, count * 4, 64);
  if (!multipliers || !bias_q || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  uint32_t shift;
  if (pa_m5_affine_metadata(scales, count, multipliers, &shift)) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  for (uint32_t i = 0; i < count; ++i) {
    int64_t rounded = pa_m5_rne_f64_signed(bias[i]);
    if (rounded < INT32_MIN || rounded > INT32_MAX) {
      pa_m5_workspace_rewind(workspace, mark); return -4;
    }
    bias_q[i] = (int32_t)rounded;
  }
  for (uint32_t offset = 0; offset < count; offset += 3072) {
    uint32_t length = count - offset < 3072 ? count - offset : 3072;
    if (backend->sfpu(backend->context, operation, length, shift, 0,
                      input + offset, (const int32_t *)(multipliers + offset),
                      bias_q + offset, result + offset)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
  }
  for (uint32_t i = 0; i < count; ++i) {
    if (result[i] < -32768 || result[i] > 32767) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    output[i] = (int16_t)result[i];
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

int pa_m5_dynamic_quantize(const int16_t *input, uint32_t rows, uint32_t columns,
                           int8_t *output, double *units) {
  if (!input || !output || !units || !rows || rows > 16 || !columns || columns > 3072) return -1;
  for (uint32_t row = 0; row < rows; ++row) {
    uint32_t maximum = 0;
    for (uint32_t column = 0; column < columns; ++column) {
      uint32_t magnitude = magnitude_i16(input[row * columns + column]);
      if (magnitude > maximum) maximum = magnitude;
    }
    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum);
    if (multiplier == UINT32_MAX) return -2;
    units[row] = pa_m5_dynamic_unit(multiplier, 1.0 / 256.0);
    for (uint32_t column = 0; column < columns; ++column) {
      int64_t product = (int64_t)input[row * columns + column] * multiplier;
      output[row * columns + column] = pa_m5_sat_i8(pa_m5_rne_i64(product, UINT64_C(1) << 24));
    }
  }
  return 0;
}

int pa_m5_smooth(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                 const int16_t *input, uint32_t rows, uint32_t columns,
                 const double *smoothing, int16_t *output, uint32_t *exponents) {
  if (!backend || !backend->sfpu || !workspace || !input || !smoothing || !output ||
      !exponents || !rows || rows > 16 || !columns || columns > 3072) return -1;
  uint32_t mark = workspace->used;
  double *scales = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  double *zero_bias = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  if (!scales || !zero_bias || !multipliers) { pa_m5_workspace_rewind(workspace, mark); return -2; }
  for (uint32_t i = 0; i < columns; ++i) { scales[i] = 1.0 / smoothing[i]; zero_bias[i] = 0.0; }
  uint32_t shift;
  if (pa_m5_affine_metadata(scales, columns, multipliers, &shift)) {
    pa_m5_workspace_rewind(workspace, mark); return -3;
  }
  int any_overflow = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    exponents[row] = 0;
    for (uint32_t i = 0; i < columns; ++i) {
      int64_t prospective = pa_m5_rne_i64((int64_t)input[row*columns+i] * multipliers[i],
                                          UINT64_C(1) << shift);
      if (prospective < -32768 || prospective > 32767) any_overflow = 1;
    }
  }
  for (uint32_t row = 0; row < rows; ++row) {
    if (any_overflow) {
      double maximum = 0.0;
      for (uint32_t i = 0; i < columns; ++i) {
        double logical = (double)input[row*columns+i] * (1.0 / smoothing[i]);
        if (logical < 0) logical = -logical;
        if (logical > maximum) maximum = logical;
      }
      exponents[row] = pa_m5_storage_exponent(maximum / 256.0);
      if (exponents[row] == UINT32_MAX) { pa_m5_workspace_rewind(workspace, mark); return -3; }
    }
    for (uint32_t i = 0; i < columns; ++i)
      scales[i] = (1.0 / smoothing[i]) / power2(exponents[row]);
    // Source int16 and destination int16 cannot be overlaid as int32 planes.
    uint32_t row_mark = workspace->used;
    int32_t *expanded = pa_m5_workspace_allocate(workspace, columns * 4, 64);
    if (!expanded) { pa_m5_workspace_rewind(workspace, mark); return -2; }
    for (uint32_t i = 0; i < columns; ++i) expanded[i] = input[row*columns+i];
    int status = affine_row(backend, workspace, expanded, scales, zero_bias, columns,
                            PA_M5_SFPU_AFFINE, output + row * columns);
    pa_m5_workspace_rewind(workspace, row_mark);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status; }
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

int pa_m5_apply_norm(const pa_m5_backend *backend, pa_m5_workspace *workspace,
               const pa_m5_norm *norm, const int16_t *input,
               const uint32_t *exponents, uint32_t rows, uint32_t columns,
               int16_t *output) {
  if (!backend || !backend->sfpu || !workspace || !norm || !input || !exponents ||
      !output || !rows || rows > 16 || !columns || columns > 3072) return -1;
  uint32_t mark = workspace->used;
  int16_t *gain = pa_m5_workspace_allocate(workspace, columns * 2, 64);
  int32_t *bias = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  int32_t *x_plane = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  int32_t *gain_plane = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  int32_t *zero = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  double *scale = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  double *affine_bias = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  if (!gain || !bias || !x_plane || !gain_plane || !zero || !result || !scale || !affine_bias) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  for (uint32_t i = 0; i < columns; ++i) zero[i] = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    uint32_t factor;
    if (pa_m5_layernorm_metadata(input + row*columns, columns, exponents[row],
                                 norm->gain, norm->bias, gain, bias, &factor)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    for (uint32_t i = 0; i < columns; ++i) {
      x_plane[i] = input[row*columns+i]; gain_plane[i] = gain[i];
    }
    const int32_t *core_bias = factor == 1 ? bias : zero;
    if (backend->sfpu(backend->context, PA_M5_SFPU_LAYERNORM, columns, 0, 0,
                      x_plane, gain_plane, core_bias, result)) {
      pa_m5_workspace_rewind(workspace, mark); return -4;
    }
    if (factor == 1) {
      for (uint32_t i = 0; i < columns; ++i) output[row*columns+i] = (int16_t)result[i];
    } else {
      for (uint32_t i = 0; i < columns; ++i) {
        x_plane[i] = (int16_t)result[i]; scale[i] = (double)factor; affine_bias[i] = (double)bias[i];
      }
      int status = affine_row(backend, workspace, x_plane, scale, affine_bias,
                              columns, PA_M5_SFPU_AFFINE, output + row*columns);
      if (status) { pa_m5_workspace_rewind(workspace, mark); return status; }
    }
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

int pa_m5_gelu(const pa_m5_backend *backend, pa_m5_workspace *workspace,
               const int16_t *input, uint32_t count, int16_t *output) {
  if (!backend || !backend->sfpu || !workspace || !input || !output || !count) return -1;
  uint32_t mark = workspace->used;
  int32_t *source = pa_m5_workspace_allocate(workspace, (count < 3072 ? count : 3072) * 4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, (count < 3072 ? count : 3072) * 4, 64);
  if (!source || !result) { pa_m5_workspace_rewind(workspace, mark); return -2; }
  for (uint32_t offset = 0; offset < count; offset += 3072) {
    uint32_t length = count - offset < 3072 ? count - offset : 3072;
    for (uint32_t i = 0; i < length; ++i) source[i] = input[offset+i];
    if (backend->sfpu(backend->context, PA_M5_SFPU_GELU, length, 0, 0,
                      source, 0, 0, result)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    for (uint32_t i = 0; i < length; ++i) output[offset+i] = (int16_t)result[i];
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

void pa_m5_cache_open(pa_m5_cache *cache, void *arena_base) {
  if (!cache || !arena_base) return;
  cache->keys = (int16_t *)((uint8_t *)arena_base + UINT32_C(205344768));
  cache->values = (int16_t *)((uint8_t *)arena_base + UINT32_C(224223232));
  cache->keys_i8 = (int8_t *)((uint8_t *)arena_base + UINT32_C(243101696));
  cache->key_units = (double *)((uint8_t *)arena_base + UINT32_C(252542976));
}
static uint64_t cache_vector(uint32_t layer, uint32_t head, uint32_t position) {
  return ((uint64_t)layer * 12 * 1024 + (uint64_t)head * 1024 + position) * 64;
}
static uint32_t maximum_i16(const int16_t *values, uint32_t count) {
  uint32_t maximum = 0;
  for (uint32_t i = 0; i < count; ++i) {
    uint32_t magnitude = magnitude_i16(values[i]);
    if (magnitude > maximum) maximum = magnitude;
  }
  return maximum;
}

int pa_m5_attention(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                    pa_m5_cache *cache, uint32_t layer, const int16_t *qkv,
                    uint32_t rows, uint32_t past, int16_t *context) {
  if (!backend || !backend->gemm_tile || !backend->sfpu || !workspace || !cache ||
      !cache->keys || !cache->values || !cache->keys_i8 || !cache->key_units ||
      !qkv || !context || layer >= 12 || !rows || rows > 16 || past + rows > 1024) return -1;
  uint32_t mark = workspace->used;
  int8_t *query_i8 = pa_m5_workspace_allocate(workspace, 64, 64);
  int8_t *weight_tile = pa_m5_workspace_allocate(workspace, 1024 * 16, 64);
  int32_t *tile_output = pa_m5_workspace_allocate(workspace, 16 * 4, 64);
  int32_t *scores_raw = pa_m5_workspace_allocate(workspace, 1024 * 4, 64);
  int16_t *scores = pa_m5_workspace_allocate(workspace, 1024 * 2, 64);
  double *scales = pa_m5_workspace_allocate(workspace, 1024 * 8, 64);
  double *zero_bias = pa_m5_workspace_allocate(workspace, 1024 * 8, 64);
  int32_t *softmax_input = pa_m5_workspace_allocate(workspace, 1024 * 4, 64);
  int32_t *probability = pa_m5_workspace_allocate(workspace, 1024 * 4, 64);
  int8_t *probability_i8 = pa_m5_workspace_allocate(workspace, 1024, 64);
  int8_t *values_i8 = pa_m5_workspace_allocate(workspace, 1024 * 64, 64);
  double *value_units = pa_m5_workspace_allocate(workspace, 64 * 8, 64);
  int32_t *value_sums = pa_m5_workspace_allocate(workspace, 64 * 4, 64);
  int16_t *value_output = pa_m5_workspace_allocate(workspace, 64 * 2, 64);
  if (!query_i8 || !weight_tile || !tile_output || !scores_raw || !scores || !scales ||
      !zero_bias || !softmax_input || !probability || !probability_i8 || !values_i8 ||
      !value_units || !value_sums || !value_output) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  for (uint32_t i = 0; i < 1024; ++i) zero_bias[i] = 0.0;
  // Publish physical cache payload beyond the externally committed length;
  // the enclosing runtime advances validity only after the token succeeds.
  for (uint32_t row = 0; row < rows; ++row) for (uint32_t head = 0; head < 12; ++head) {
    uint64_t destination = cache_vector(layer, head, past + row);
    const int16_t *source = qkv + row*2304 + head*64;
    for (uint32_t feature = 0; feature < 64; ++feature) {
      cache->keys[destination+feature] = source[768+feature];
      cache->values[destination+feature] = source[1536+feature];
    }
    uint32_t maximum = maximum_i16(cache->keys + destination, 64);
    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum);
    if (multiplier == UINT32_MAX) { pa_m5_workspace_rewind(workspace, mark); return -3; }
    cache->key_units[((uint64_t)layer*12+head)*1024+past+row] =
        pa_m5_dynamic_unit(multiplier, 1.0/256.0);
    for (uint32_t feature = 0; feature < 64; ++feature)
      cache->keys_i8[destination+feature] = pa_m5_sat_i8(pa_m5_rne_i64(
          (int64_t)cache->keys[destination+feature]*multiplier, UINT64_C(1)<<24));
  }
  for (uint32_t row = 0; row < rows; ++row) for (uint32_t head = 0; head < 12; ++head) {
    uint32_t length = past + row + 1;
    const int16_t *query = qkv + row*2304 + head*64;
    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum_i16(query, 64));
    if (multiplier == UINT32_MAX) { pa_m5_workspace_rewind(workspace, mark); return -3; }
    double query_unit = pa_m5_dynamic_unit(multiplier, 1.0/256.0);
    for (uint32_t feature = 0; feature < 64; ++feature)
      query_i8[feature] = pa_m5_sat_i8(pa_m5_rne_i64((int64_t)query[feature]*multiplier,
                                                    UINT64_C(1)<<24));
    for (uint32_t tile = 0; tile < (length+15)/16; ++tile) {
      uint32_t width = length-tile*16 < 16 ? length-tile*16 : 16;
      for (uint32_t feature = 0; feature < 64; ++feature)
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[feature*16+column] = column < width ? cache->keys_i8[
              cache_vector(layer,head,tile*16+column)+feature] : 0;
      if (backend->gemm_tile(backend->context, 1, 64, width, query_i8,
                             weight_tile, tile_output)) {
        pa_m5_workspace_rewind(workspace, mark); return -4;
      }
      for (uint32_t column = 0; column < width; ++column)
        scores_raw[tile*16+column] = tile_output[column];
    }
    int64_t maximum_score = INT64_MIN;
    uint32_t score_shift;
    for (uint32_t position = 0; position < length; ++position)
      scales[position] = query_unit * cache->key_units[((uint64_t)layer*12+head)*1024+position] * 32.0;
    uint32_t *score_multipliers = pa_m5_workspace_allocate(workspace, length*4, 64);
    if (!score_multipliers || pa_m5_affine_metadata(scales, length, score_multipliers, &score_shift)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    for (uint32_t position = 0; position < length; ++position) {
      int64_t raw = pa_m5_rne_i64((int64_t)scores_raw[position]*score_multipliers[position],
                                  UINT64_C(1)<<score_shift);
      if (raw > maximum_score) maximum_score = raw;
    }
    if (maximum_score < INT32_MIN || maximum_score > INT32_MAX) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    for (uint32_t position = 0; position < length; ++position) zero_bias[position] = -(double)maximum_score;
    // Release the explicit metadata probe; affine_row recomputes the same common metadata.
    workspace->used = (uint32_t)((uint8_t *)score_multipliers - workspace->base);
    int status = affine_row(backend, workspace, scores_raw, scales, zero_bias, length,
                            PA_M5_SFPU_AFFINE, scores);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status - 10; }
    for (uint32_t position = 0; position < length; ++position)
      softmax_input[position] = UINT32_C(0x10000) | (uint16_t)scores[position];
    if (backend->sfpu(backend->context, PA_M5_SFPU_SOFTMAX, length, 0, 0,
                      softmax_input, 0, 0, probability)) {
      pa_m5_workspace_rewind(workspace, mark); return -5;
    }
    uint32_t probability_maximum = 0;
    for (uint32_t position = 0; position < length; ++position)
      if ((uint32_t)probability[position] > probability_maximum)
        probability_maximum = (uint32_t)probability[position];
    multiplier = pa_m5_dynamic_multiplier(probability_maximum);
    double probability_unit = pa_m5_dynamic_unit(multiplier, 1.0/32768.0);
    for (uint32_t position = 0; position < length; ++position)
      probability_i8[position] = pa_m5_sat_i8(pa_m5_rne_i64(
          (int64_t)probability[position]*multiplier, UINT64_C(1)<<24));
    for (uint32_t feature = 0; feature < 64; ++feature) {
      uint32_t maximum = 0;
      for (uint32_t position = 0; position < length; ++position) {
        int16_t value = cache->values[cache_vector(layer,head,position)+feature];
        uint32_t magnitude = magnitude_i16(value); if (magnitude > maximum) maximum = magnitude;
      }
      multiplier = pa_m5_dynamic_multiplier(maximum);
      value_units[feature] = pa_m5_dynamic_unit(multiplier, 1.0/256.0);
      for (uint32_t position = 0; position < length; ++position)
        values_i8[position*64+feature] = pa_m5_sat_i8(pa_m5_rne_i64(
            (int64_t)cache->values[cache_vector(layer,head,position)+feature]*multiplier,
            UINT64_C(1)<<24));
    }
    for (uint32_t tile = 0; tile < 4; ++tile) {
      for (uint32_t position = 0; position < length; ++position)
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[position*16+column] = values_i8[position*64+tile*16+column];
      if (backend->gemm_tile(backend->context, 1, length, 16, probability_i8,
                             weight_tile, tile_output)) {
        pa_m5_workspace_rewind(workspace, mark); return -4;
      }
      for (uint32_t column = 0; column < 16; ++column)
        value_sums[tile*16+column] = tile_output[column];
    }
    for (uint32_t feature = 0; feature < 64; ++feature)
      { scales[feature] = probability_unit * value_units[feature] * 256.0;
        zero_bias[feature] = 0.0; }
    status = affine_row(backend, workspace, value_sums, scales, zero_bias, 64,
                        PA_M5_SFPU_AFFINE, value_output);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status - 20; }
    for (uint32_t feature = 0; feature < 64; ++feature)
      context[row*768+head*64+feature] = value_output[feature];
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

int pa_m5_project(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                  const pa_m5_linear *linear, const int16_t *input,
                  const uint32_t *input_exponents, uint32_t rows,
                  int scaled, const int16_t *residual,
                  const uint32_t *residual_exponents,
                  int16_t *output, uint32_t *output_exponents) {
  if (!backend || !backend->gemm_tile || !backend->sfpu || !workspace || !linear ||
      !input || !input_exponents || !output || !output_exponents || !rows || rows > 16 ||
      !linear->k || linear->k > 3072 || !linear->n || linear->n > 50257 ||
      ((residual == 0) != (residual_exponents == 0))) return -1;
  uint32_t mark = workspace->used, k = linear->k, n = linear->n;
  int8_t *quantized = pa_m5_workspace_allocate(workspace, rows * k, 64);
  double *units = pa_m5_workspace_allocate(workspace, rows * 8, 64);
  int32_t *sums = pa_m5_workspace_allocate(workspace, rows * n * 4, 64);
  int32_t *tile_output = pa_m5_workspace_allocate(workspace, rows * 16 * 4, 64);
  double *scales = pa_m5_workspace_allocate(workspace, n * 8, 64);
  double *bias = pa_m5_workspace_allocate(workspace, n * 8, 64);
  if (!quantized || !units || !sums || !tile_output || !scales || !bias) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  if (pa_m5_dynamic_quantize(input, rows, k, quantized, units)) {
    pa_m5_workspace_rewind(workspace, mark); return -3;
  }
  for (uint32_t tile = 0; tile < (n + 15) / 16; ++tile) {
    uint32_t width = n - tile * 16 < 16 ? n - tile * 16 : 16;
    if (backend->gemm_tile(backend->context, rows, k, width, quantized,
                           linear->tiles + (uint64_t)tile * k * 16, tile_output)) {
      pa_m5_workspace_rewind(workspace, mark); return -4;
    }
    for (uint32_t row = 0; row < rows; ++row)
      for (uint32_t column = 0; column < width; ++column)
        sums[row*n + tile*16 + column] = tile_output[row*16 + column];
  }
  for (uint32_t row = 0; row < rows; ++row) {
    if (!scaled && !residual) {
      output_exponents[row] = 0;
      for (uint32_t i = 0; i < n; ++i) {
        double channel_scale = units[row] * linear->scale[i];
        channel_scale *= power2(input_exponents[row]);
        scales[i] = channel_scale * 256.0;
        bias[i] = linear->bias[i] * 256.0;
      }
    } else {
      double maximum = 0.0;
      for (uint32_t i = 0; i < n; ++i) {
        double channel_scale = units[row] * linear->scale[i];
        channel_scale *= power2(input_exponents[row]);
        double logical = (double)sums[row*n+i] * channel_scale + linear->bias[i];
        if (logical < 0) logical = -logical;
        if (residual) {
          double old = (double)residual[row*n+i] * power2(residual_exponents[row]) / 256.0;
          if (old < 0) old = -old;
          logical += old;
        }
        if (logical > maximum) maximum = logical;
      }
      uint32_t exponent = pa_m5_storage_exponent(maximum);
      if (exponent == UINT32_MAX) { pa_m5_workspace_rewind(workspace, mark); return -5; }
      output_exponents[row] = exponent;
      double inverse_unit = 256.0 / power2(exponent);
      for (uint32_t i = 0; i < n; ++i) {
        double channel_scale = units[row] * linear->scale[i];
        channel_scale *= power2(input_exponents[row]);
        scales[i] = channel_scale * inverse_unit;
        bias[i] = linear->bias[i] * inverse_unit;
      }
    }
    int status = affine_row(backend, workspace, sums + row*n, scales, bias, n,
                            PA_M5_SFPU_AFFINE, output + row*n);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status; }
    if (residual) {
      uint32_t row_mark = workspace->used;
      int32_t *expanded = pa_m5_workspace_allocate(workspace, n * 4, 64);
      int16_t *aligned = pa_m5_workspace_allocate(workspace, n * 2, 64);
      if (!expanded || !aligned) { pa_m5_workspace_rewind(workspace, mark); return -2; }
      double align_scale = power2(residual_exponents[row]) / power2(output_exponents[row]);
      for (uint32_t i = 0; i < n; ++i) {
        expanded[i] = residual[row*n+i]; scales[i] = align_scale; bias[i] = 0.0;
      }
      status = affine_row(backend, workspace, expanded, scales, bias, n,
                          PA_M5_SFPU_AFFINE, aligned);
      if (!status) {
        for (uint32_t i = 0; i < n; ++i) expanded[i] = output[row*n+i];
        int32_t *second = pa_m5_workspace_allocate(workspace, n * 4, 64);
        int32_t *sum_output = pa_m5_workspace_allocate(workspace, n * 4, 64);
        if (!second || !sum_output) status = -2;
        else {
          for (uint32_t i = 0; i < n; ++i) second[i] = aligned[i];
          for (uint32_t offset = 0; offset < n; offset += 3072) {
            uint32_t length = n - offset < 3072 ? n - offset : 3072;
            if (backend->sfpu(backend->context, PA_M5_SFPU_ADD, length, 0, 0,
                              expanded+offset, second+offset, 0, sum_output+offset)) status = -3;
          }
          if (!status) for (uint32_t i = 0; i < n; ++i) output[row*n+i] = (int16_t)sum_output[i];
        }
      }
      if (status) { pa_m5_workspace_rewind(workspace, mark); return status; }
      pa_m5_workspace_rewind(workspace, row_mark);
    }
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

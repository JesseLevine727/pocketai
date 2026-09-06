#include "pa_m5_numerics.h"
static int finite_value(double value) {
  union { double floating; uint64_t bits; } representation = {.floating = value};
  return ((representation.bits >> 52) & 0x7ffu) != 0x7ffu;
}
static double absolute_value(double value) {
  union { double floating; uint64_t bits; } representation = {.floating = value};
  representation.bits &= UINT64_C(0x7fffffffffffffff);
  return representation.floating;
}

uint64_t pa_m5_rne_u64(uint64_t numerator, uint64_t denominator) {
  if (!denominator) return UINT64_MAX;
  uint64_t q = numerator / denominator, r = numerator % denominator;
  return q + (r > denominator - r || (r == denominator - r && (q & 1u)));
}

int64_t pa_m5_rne_i64(int64_t numerator, uint64_t denominator) {
  if (!denominator || numerator == INT64_MIN) return INT64_MIN;
  uint64_t magnitude = numerator < 0 ? (uint64_t)-numerator : (uint64_t)numerator;
  uint64_t rounded = pa_m5_rne_u64(magnitude, denominator);
  if (rounded > INT64_MAX) return INT64_MIN;
  return numerator < 0 ? -(int64_t)rounded : (int64_t)rounded;
}

uint64_t pa_m5_rne_f64(double value) {
  union { double floating; uint64_t bits; } representation = {.floating = value};
  uint64_t bits = representation.bits;
  if ((bits << 1) == 0) return 0; // Treat +0.0 and -0.0 identically.
  uint64_t fraction = bits & UINT64_C(0x000fffffffffffff);
  unsigned encoded = (unsigned)((bits >> 52) & 0x7ffu);
  if ((bits >> 63) || encoded == 0x7ffu) return UINT64_MAX;
  if (!encoded) return 0; // Every nonnegative subnormal is below 0.5.
  int exponent = (int)encoded - 1023;
  uint64_t mantissa = fraction | UINT64_C(0x0010000000000000);
  if (exponent < -1) return 0;
  if (exponent == -1)
    return fraction ? 1 : 0; // exactly 0.5 ties to even zero
  if (exponent >= 64) return UINT64_MAX;
  if (exponent >= 52) {
    if (mantissa > (UINT64_MAX >> (exponent - 52))) return UINT64_MAX;
    return mantissa << (exponent - 52);
  }
  unsigned shift = (unsigned)(52 - exponent);
  uint64_t q = mantissa >> shift, remainder = mantissa & ((UINT64_C(1) << shift) - 1);
  uint64_t half = UINT64_C(1) << (shift - 1);
  return q + (remainder > half || (remainder == half && (q & 1u)));
}

int64_t pa_m5_rne_f64_signed(double value) {
  if (value == 0.0) return 0;
  if (value >= 0) {
    uint64_t result = pa_m5_rne_f64(value);
    return result <= INT64_MAX ? (int64_t)result : INT64_MIN;
  }
  uint64_t magnitude = pa_m5_rne_f64(-value);
  return magnitude <= INT64_MAX ? -(int64_t)magnitude : INT64_MIN;
}

int16_t pa_m5_sat_i16(int64_t value) {
  return value < -32768 ? -32768 : value > 32767 ? 32767 : (int16_t)value;
}
int8_t pa_m5_sat_i8(int64_t value) {
  return value < -128 ? -128 : value > 127 ? 127 : (int8_t)value;
}

uint32_t pa_m5_dynamic_multiplier(uint32_t maximum) {
  if (!maximum) return 0;
  uint64_t result = pa_m5_rne_u64(UINT64_C(127) << 24, maximum);
  return result < UINT32_C(0x80000000) ? (uint32_t)result : UINT32_MAX;
}

double pa_m5_dynamic_unit(uint32_t multiplier, double input_unit) {
  return multiplier ? (16777216.0 / (double)multiplier) * input_unit : 1.0;
}

int pa_m5_affine_metadata(const double *scales, uint32_t count,
                          uint32_t *multipliers, uint32_t *shift) {
  if (!scales || !count || !multipliers || !shift) return -1;
  uint32_t selected = 31;
  for (;;) {
    int valid = 1;
    double factor = (double)(UINT64_C(1) << selected);
    for (uint32_t i = 0; i < count; ++i) {
      uint64_t rounded = pa_m5_rne_f64(scales[i] * factor);
      if (!(scales[i] >= 0.0) || !finite_value(scales[i]) || rounded >= UINT32_C(0x80000000)) {
        valid = 0; break;
      }
    }
    if (valid || !selected) break;
    --selected;
  }
  double factor = (double)(UINT64_C(1) << selected);
  for (uint32_t i = 0; i < count; ++i) {
    uint64_t rounded = pa_m5_rne_f64(scales[i] * factor);
    if (!(scales[i] >= 0.0) || !finite_value(scales[i]) || rounded >= UINT32_C(0x80000000) ||
        (!rounded && scales[i] != 0.0)) return -2;
    multipliers[i] = (uint32_t)rounded;
  }
  *shift = selected;
  return 0;
}

uint32_t pa_m5_storage_exponent(double maximum) {
  if (!(maximum >= 0.0) || !finite_value(maximum)) return UINT32_MAX;
  uint32_t exponent = 0;
  while (maximum * 256.0 > 32700.0 * (double)(UINT64_C(1) << exponent)) {
    if (exponent == 30) return UINT32_MAX;
    ++exponent;
  }
  return exponent;
}

typedef struct { uint64_t high, low; } wide_unsigned;
static wide_unsigned square_u54(uint64_t value) {
  uint64_t low = value & UINT64_C(0xffffffff), high = value >> 32;
  uint64_t p0 = low * low, cross = 2 * low * high;
  uint64_t result_low = p0 + (cross << 32);
  wide_unsigned result = {high * high + (cross >> 32) + (result_low < p0), result_low};
  return result;
}
static int wide_compare(wide_unsigned lhs, wide_unsigned rhs) {
  if (lhs.high != rhs.high) return lhs.high < rhs.high ? -1 : 1;
  return lhs.low < rhs.low ? -1 : lhs.low > rhs.low ? 1 : 0;
}
// Correctly rounded binary64 square root for the positive-normal metadata
// domain, implemented with integer comparisons so RV32 needs no F/D/libm.
double pa_m5_sqrt_f64(double value) {
  union { double floating; uint64_t bits; } input = {.floating = value}, output;
  unsigned encoded = (unsigned)((input.bits >> 52) & 0x7ffu);
  if (!encoded || encoded == 0x7ffu || (input.bits >> 63)) return 0.0;
  int exponent = (int)encoded - 1023;
  uint64_t significand = (input.bits & UINT64_C(0x000fffffffffffff)) |
                         UINT64_C(0x0010000000000000);
  if (exponent & 1) { significand <<= 1; --exponent; }
  wide_unsigned radicand = {significand >> 12, significand << 52};
  uint64_t low = UINT64_C(1) << 52, high = (UINT64_C(1) << 53) - 1;
  while (low < high) {
    uint64_t middle = low + (high - low + 1) / 2;
    if (wide_compare(square_u54(middle), radicand) <= 0) low = middle;
    else high = middle - 1;
  }
  // Compare (2*floor+1)^2 with four times the radicand.
  wide_unsigned four = {radicand.high << 2 | radicand.low >> 62, radicand.low << 2};
  if (wide_compare(square_u54((low << 1) + 1), four) < 0) ++low;
  int result_exponent = exponent / 2;
  if (low == (UINT64_C(1) << 53)) { low >>= 1; ++result_exponent; }
  output.bits = (uint64_t)(result_exponent + 1023) << 52 |
                (low & UINT64_C(0x000fffffffffffff));
  return output.floating;
}

int pa_m5_layernorm_metadata(const int16_t *values, uint32_t count,
                             uint32_t exponent, const double *gain,
                             const double *bias, int16_t *gain_q12,
                             int32_t *bias_q8, uint32_t *factor_out) {
  if (!values || !gain || !bias || !gain_q12 || !bias_q8 || !factor_out ||
      !count || count > 3072 || exponent > 30) return -1;
  int64_t total = 0;
  uint64_t squares = 0;
  for (uint32_t i = 0; i < count; ++i) {
    int64_t value = values[i]; total += value; squares += (uint64_t)(value * value);
  }
  uint64_t variance = (uint64_t)count * squares - (uint64_t)(total * total);
  double epsilon = 1.0e-5 * 65536.0 * (double)(count * count);
  double divisor = (double)(UINT64_C(1) << (2 * exponent));
  double correction = pa_m5_sqrt_f64(((double)variance + epsilon) /
                                     ((double)variance + epsilon / divisor));
  if (!finite_value(correction)) return -2;
  uint32_t factor = 1;
  for (;;) {
    double maximum = 0.0;
    for (uint32_t i = 0; i < count; ++i) {
      double corrected = absolute_value(gain[i] * correction / (double)factor);
      if (corrected > maximum) maximum = corrected;
    }
    if (maximum <= 32767.0 / 4096.0) break;
    if (factor >= UINT32_C(1) << 30) return -2;
    factor <<= 1;
  }
  for (uint32_t i = 0; i < count; ++i) {
    int64_t g = pa_m5_rne_f64_signed(gain[i] * correction * 4096.0 / (double)factor);
    int64_t b = pa_m5_rne_f64_signed(bias[i] * 256.0);
    if (g < -32768 || g > 32767 || b < INT32_MIN || b > INT32_MAX) return -2;
    gain_q12[i] = (int16_t)g; bias_q8[i] = (int32_t)b;
  }
  *factor_out = factor;
  return 0;
}

static uint32_t word(const uint8_t *base, uint32_t offset) {
  return (uint32_t)base[offset] | (uint32_t)base[offset+1] << 8 |
         (uint32_t)base[offset+2] << 16 | (uint32_t)base[offset+3] << 24;
}
static int digest_equal(const uint8_t *actual, const uint8_t expected[32]) {
  uint8_t difference = 0;
  for (unsigned i = 0; i < 32; ++i) difference |= actual[i] ^ expected[i];
  return difference == 0;
}

static int expected_array(uint32_t id, uint32_t *dtype, uint32_t *rank,
                          uint32_t shape[3]) {
  shape[0] = shape[1] = shape[2] = 0;
  if (id == 0 || id == 1) {
    *dtype = 2; *rank = 2; shape[0] = id ? 1024 : 50257; shape[1] = 768; return 1;
  }
  if (id >= 2 && id < 242) {
    uint32_t item = (id - 2) % 20;
    if (item >= 16) {
      *dtype = 3; *rank = 1; shape[0] = 768; return 1;
    }
    uint32_t operation = item / 4, member = item % 4;
    uint32_t k = operation == 3 ? 3072 : 768;
    uint32_t n = operation == 0 ? 2304 : operation == 2 ? 3072 : 768;
    *dtype = member ? 3 : 1;
    *rank = member ? 1 : 3;
    shape[0] = member == 3 ? k : member ? n : (n + 15) / 16;
    if (!member) { shape[1] = k; shape[2] = 16; }
    return 1;
  }
  if (id == 242 || id == 243) {
    *dtype = 3; *rank = 1; shape[0] = 768; return 1;
  }
  if (id >= 244 && id <= 247) {
    uint32_t member = id - 244;
    *dtype = member ? 3 : 1; *rank = member ? 1 : 3;
    shape[0] = member == 3 ? 768 : member ? 50257 : 3142;
    if (!member) { shape[1] = 768; shape[2] = 16; }
    return 1;
  }
  return 0;
}

int pa_m5_arena_open(pa_m5_arena *arena, const void *bytes, uint32_t length) {
  static const uint8_t pack[32] = {0xd2,0xaa,0xfe,0xff,0xd3,0xe4,0xb8,0xa1,0x34,0xb8,0xe4,0x87,0x96,0xa1,0xb0,0xcf,0x8f,0x29,0x6a,0x3b,0xd1,0x50,0xb7,0x9f,0x07,0xe2,0xde,0x03,0x7f,0xae,0x8f,0xd6};
  static const uint8_t candidate[32] = {0xa8,0xd8,0x0d,0x03,0xc1,0xaa,0xcc,0x8a,0x40,0xf0,0xf8,0x49,0x62,0xac,0xd4,0x03,0x3f,0x0a,0x1a,0xfb,0x13,0x43,0xfd,0x9e,0x1a,0xb0,0xe9,0xc5,0x0d,0x0c,0x39,0x7d};
  const uint8_t *base = bytes;
  if (!arena || !base || length != PA_M5_ARENA_BYTES ||
      word(base,0) != UINT32_C(0x354d4150) || word(base,4) != 1 ||
      word(base,8) != 65536 || word(base,12) != length ||
      word(base,16) != PA_M5_ARRAY_COUNT || word(base,20) != 32 || word(base,24) != 128 ||
      word(base,28) != PA_M5_REGION_COUNT || word(base,32) != 32 || word(base,36) != 8192 ||
      word(base,44) != 1024 || word(base,48) != 12 || word(base,52) != 12 ||
      word(base,40) != 205340672 || word(base,56) != 768 || word(base,60) != 50257 ||
      !digest_equal(base+64, pack) || !digest_equal(base+96, candidate)) return -1;
  uint32_t previous_end = 65536;
  for (uint32_t id = 0; id < PA_M5_ARRAY_COUNT; ++id) {
    uint32_t offset = 128 + id * 32, array_offset = word(base, offset+4);
    uint32_t size = word(base, offset+8), dtype = word(base, offset+12), rank = word(base, offset+16);
    uint32_t width = dtype == 1 ? 1 : dtype == 2 ? 2 : dtype == 3 ? 8 : 0;
    uint32_t expected_dtype, expected_rank, expected_shape[3];
    uint64_t elements = 1;
    if (!expected_array(id, &expected_dtype, &expected_rank, expected_shape) ||
        word(base,offset) != id || dtype != expected_dtype || rank != expected_rank ||
        !width || array_offset != (previous_end + 63u) / 64u * 64u) return -2;
    for (uint32_t axis = 0; axis < 3; ++axis) {
      uint32_t extent = word(base, offset+20+axis*4);
      if (extent != expected_shape[axis]) return -2;
      if (axis < rank) elements *= extent;
    }
    uint64_t end = (uint64_t)array_offset + size;
    if (elements * width != size || array_offset < previous_end || end > word(base,40)) return -2;
    previous_end = (uint32_t)end;
  }
  static const uint32_t region_offsets[PA_M5_REGION_COUNT] = {
    0,205340672,205344768,224219136,224223232,243097600,243101696,252538880,
    252542976,253722624,253726720,257921024,257925120,266313728,266317824};
  static const uint32_t region_bytes[PA_M5_REGION_COUNT] = {
    205340672,4096,18874368,4096,18874368,4096,9437184,4096,1179648,4096,
    4194304,4096,8388608,4096,2117632};
  static const uint32_t region_permissions[PA_M5_REGION_COUNT] = {
    1,0,3,0,3,0,3,0,3,0,3,0,3,0,0};
  for (uint32_t id = 0; id < PA_M5_REGION_COUNT; ++id) {
    uint32_t offset = 8192 + id * 32;
    if (word(base,offset) != id || word(base,offset+4) != region_offsets[id] ||
        word(base,offset+8) != region_bytes[id] ||
        word(base,offset+12) != region_permissions[id] || word(base,offset+16) ||
        word(base,offset+20) || word(base,offset+24) || word(base,offset+28)) return -3;
  }
  arena->base = base; arena->bytes = length; arena->header = (const uint32_t *)bytes;
  return 0;
}

const void *pa_m5_arena_array(const pa_m5_arena *arena, uint32_t id,
                              uint32_t *payload_bytes) {
  if (!arena || !arena->base || id >= PA_M5_ARRAY_COUNT) return 0;
  uint32_t entry = 128 + id * 32;
  if (payload_bytes) *payload_bytes = word(arena->base, entry+8);
  return arena->base + word(arena->base, entry+4);
}

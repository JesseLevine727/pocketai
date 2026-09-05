/* M4 native CPU implementation of the unchanged M3 SFPU v1 packet arithmetic.
 * Used for the practical same-board CPU baseline, not as an FPGA golden.
 * LUTs are supplied by the pinned reference/manifest, never refitted here.
 */
#include <stdint.h>
#include <stddef.h>
#include <math.h>

static uint64_t uround(uint64_t value, uint64_t denominator) {
    uint64_t q = value / denominator, r = value % denominator;
    return q + (2 * r > denominator || (2 * r == denominator && (q & 1)));
}

static int64_t sround(int64_t value, uint64_t denominator) {
    uint64_t magnitude = value < 0 ? (uint64_t)(-value) : (uint64_t)value;
    int64_t rounded = (int64_t)uround(magnitude, denominator);
    return value < 0 ? -rounded : rounded;
}

static int32_t sat16(int64_t value) {
    return value < -32768 ? -32768 : value > 32767 ? 32767 : (int32_t)value;
}

/* Compare root^2 with an unsigned up-to-80-bit {hi,lo} radicand, without
 * requiring __int128 (not available on the 32-bit ARM target). root<2^40.
 */
static int square_compare(uint64_t root, uint64_t hi, uint64_t lo) {
    uint64_t a = root & UINT64_C(0xffffffff), b = root >> 32;
    uint64_t low = a * a, cross = 2 * a * b;
    uint64_t sum = low + (cross << 32);
    uint64_t high = b * b + (cross >> 32) + (sum < low);
    if (high != hi) return high < hi ? -1 : 1;
    return sum < lo ? -1 : sum > lo ? 1 : 0;
}

static uint64_t ln_denominator(uint64_t variance, uint64_t epsilon) {
    uint64_t lo = variance << 24;
    uint64_t hi = variance >> 40;
    uint64_t sum = lo + epsilon;
    hi += sum < lo;
    /* FP only seeds the CPU integer-root search; exact integer comparisons
     * correct the result. Final arithmetic is independent of seed rounding.
     */
    uint64_t root = (uint64_t)sqrtl((long double)variance * 16777216.0L + (long double)epsilon);
    while (square_compare(root, hi, sum) > 0) --root;
    while (square_compare(root + 1, hi, sum) <= 0) ++root;
    return root;
}

static int32_t gelu(int32_t x, const int16_t *table) {
    int32_t magnitude = x < 0 ? -x : x;
    int32_t positive = magnitude <= 2048 ? table[magnitude] : magnitude;
    return x < 0 ? positive - magnitude : positive;
}

static uint32_t exponential(int difference, const uint32_t *table) {
    if (difference >= 4096) return 0;
    int index = difference / 16, fraction = difference % 16;
    return (uint32_t)uround((uint64_t)table[index] * (16 - fraction) +
                            (uint64_t)table[index + 1] * fraction, 16);
}

int pa_m4_sfpu(int op, int length, int shift, uint32_t multiplier,
               const int32_t *input, int32_t *output,
               const int16_t *gelu_table, const uint32_t *exp_table) {
    if (!input || !output || !gelu_table || !exp_table || op < 1 || op > 7 ||
        length < 1 || length > (op == 3 ? 1024 : 3072)) return -1;
    if (op == 4 || op == 6) {
        if (shift < 0 || shift > 31 || multiplier) return -2;
    } else if (op == 5) {
        if (shift < 0 || shift > 31 || multiplier >= UINT32_C(0x80000000)) return -2;
    } else if (shift || multiplier) return -2;

    if (op == 2) {
        int64_t total = 0;
        uint64_t squares = 0;
        for (int i = 0; i < length; ++i) {
            int64_t x = (int16_t)input[i];
            total += x; squares += (uint64_t)(x * x);
        }
        uint64_t variance = (uint64_t)length * squares - (uint64_t)(total * total);
        uint64_t epsilon = uround(((uint64_t)length * (uint64_t)length) << 40, 100000);
        uint64_t denominator = ln_denominator(variance, epsilon);
        if (!denominator) return -3;
        for (int i = 0; i < length; ++i) {
            int64_t numerator = ((int64_t)length * (int16_t)input[i] - total) *
                                (int16_t)input[length + i] * 256;
            output[i] = sat16(sround(numerator, denominator) + (int16_t)input[2 * length + i]);
        }
    } else if (op == 3) {
        int maximum = -32768, valid_count = 0;
        uint32_t weights[1024];
        uint64_t total = 0;
        for (int i = 0; i < length; ++i) {
            int x = (int16_t)input[i];
            if (((uint32_t)input[i] >> 16) & 1) {
                if (x > maximum) maximum = x;
                ++valid_count;
            }
        }
        if (!valid_count) {
            for (int i = 0; i < length; ++i) output[i] = 0;
            return 0;
        }
        for (int i = 0; i < length; ++i) {
            weights[i] = (((uint32_t)input[i] >> 16) & 1) ?
                          exponential(maximum - (int16_t)input[i], exp_table) : 0;
            total += weights[i];
        }
        int remainder = 32768;
        for (int i = 0; i < length; ++i) {
            output[i] = (int32_t)(((uint64_t)weights[i] * 32768) / total);
            remainder -= output[i];
        }
        for (int i = 0; i < length && remainder; ++i)
            if (weights[i]) { ++output[i]; --remainder; }
        if (remainder) return -4;
    } else {
        for (int i = 0; i < length; ++i) {
            if (op == 1) output[i] = gelu((int16_t)input[i], gelu_table);
            else if (op == 7) output[i] = sat16((int32_t)(int16_t)input[i] + (int16_t)input[length + i]);
            else if (op == 5) {
                int64_t value = sround((int64_t)input[i] * multiplier, UINT64_C(1) << shift);
                output[i] = value < -128 ? -128 : value > 127 ? 127 : (int32_t)value;
            } else {
                if (input[length + i] < 0) return -2;
                int64_t value = sround((int64_t)input[i] * input[length + i], UINT64_C(1) << shift) + input[2 * length + i];
                output[i] = sat16(value);
                if (op == 6) output[i] = gelu(output[i], gelu_table);
            }
        }
    }
    return 0;
}

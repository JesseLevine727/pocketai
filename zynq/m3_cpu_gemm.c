/* Single-thread Cortex-A9 NEON baseline. Exact int8 products, int32 reduction,
 * one final int16 saturation. No packing or model-specific approximations.
 * Portable fallback permits native-host reference testing of the same ABI.
 */
#include <stdint.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

const char *pa_cpu_backend(void) {
#if defined(__ARM_NEON)
    return "single-thread Cortex-A9 NEON, 16-column register tile, row-major";
#else
    return "single-thread portable C, row-major";
#endif
}

int pa_cpu_gemm(const int8_t *a, const int8_t *b, int16_t *c,
                int m, int n, int k) {
    if (!a || !b || !c || m < 1 || m > 16 || n < 1 || n > 3072 ||
        k < 1 || k > 3072) return -1;
    for (int row = 0; row < m; ++row) {
        int col = 0;
#if defined(__ARM_NEON)
        for (; col + 16 <= n; col += 16) {
            int32x4_t s0 = vdupq_n_s32(0), s1 = vdupq_n_s32(0);
            int32x4_t s2 = vdupq_n_s32(0), s3 = vdupq_n_s32(0);
            for (int inner = 0; inner < k; ++inner) {
                int8x8_t av = vdup_n_s8(a[row * k + inner]);
                int8x16_t bv = vld1q_s8(b + inner * n + col);
                int16x8_t p0 = vmull_s8(av, vget_low_s8(bv));
                int16x8_t p1 = vmull_s8(av, vget_high_s8(bv));
                /* Widen each product BEFORE adding: int16 pair sums can
                 * overflow for two (-128)*(-128) products. */
                s0 = vaddw_s16(s0, vget_low_s16(p0));
                s1 = vaddw_s16(s1, vget_high_s16(p0));
                s2 = vaddw_s16(s2, vget_low_s16(p1));
                s3 = vaddw_s16(s3, vget_high_s16(p1));
            }
            vst1q_s16(c + row * n + col,
                      vcombine_s16(vqmovn_s32(s0), vqmovn_s32(s1)));
            vst1q_s16(c + row * n + col + 8,
                      vcombine_s16(vqmovn_s32(s2), vqmovn_s32(s3)));
        }
#endif
        for (; col < n; ++col) {
            int32_t sum = 0;
            for (int inner = 0; inner < k; ++inner)
                sum += (int32_t)a[row * k + inner] * b[inner * n + col];
            c[row * n + col] = (int16_t)(sum < -32768 ? -32768 :
                                        sum > 32767 ? 32767 : sum);
        }
    }
    return 0;
}

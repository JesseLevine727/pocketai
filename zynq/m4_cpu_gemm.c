/* M4 exact wide W8A8 CPU comparison kernel. No saturation before int32 output.
 * B layout: [ceil(N/16), K, 16], same compact model-pack tiles as the FPGA.
 * All sums fit signed 27 bits for K<=3072. ARMv7 uses NEON widening products;
 * portable C is independently exercised on the host, not called ARM evidence.
 */
#include <stdint.h>
#include <stddef.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

const char *pa_m4_cpu_backend(void) {
#if defined(__ARM_NEON)
    return "ARMv7 NEON int8 widening multiply/int32 accumulate, N16 tiled";
#else
    return "portable C int8 multiply/int32 accumulate, N16 tiled";
#endif
}

int pa_m4_gemm(const int8_t *a, const int8_t *b, int32_t *c,
               int m, int k, int n) {
    if (!a || !b || !c || m < 1 || m > 16 || k < 1 || k > 3072 ||
        n < 1 || n > 50257) return -1;
    const int tiles = (n + 15) / 16;
    for (int t = 0; t < tiles; ++t) {
        const int width = n - t * 16 < 16 ? n - t * 16 : 16;
        const int8_t *bt = b + (size_t)t * (size_t)k * 16;
        for (int row = 0; row < m; ++row) {
            const int8_t *ar = a + (size_t)row * (size_t)k;
            int32_t sum[16] = {0};
#if defined(__ARM_NEON)
            int32x4_t s0 = vdupq_n_s32(0), s1 = s0, s2 = s0, s3 = s0;
            for (int j = 0; j < k; ++j) {
                const int8_t *bj = bt + (size_t)j * 16;
                int8x8_t av = vdup_n_s8(ar[j]);
                int16x8_t p0 = vmull_s8(av, vld1_s8(bj));
                int16x8_t p1 = vmull_s8(av, vld1_s8(bj + 8));
                s0 = vaddw_s16(s0, vget_low_s16(p0));
                s1 = vaddw_s16(s1, vget_high_s16(p0));
                s2 = vaddw_s16(s2, vget_low_s16(p1));
                s3 = vaddw_s16(s3, vget_high_s16(p1));
            }
            vst1q_s32(sum, s0); vst1q_s32(sum + 4, s1);
            vst1q_s32(sum + 8, s2); vst1q_s32(sum + 12, s3);
#else
            for (int j = 0; j < k; ++j) {
                const int8_t *bj = bt + (size_t)j * 16;
                for (int col = 0; col < 16; ++col)
                    sum[col] += (int32_t)ar[j] * (int32_t)bj[col];
            }
#endif
            for (int col = 0; col < width; ++col)
                c[(size_t)row * (size_t)n + (size_t)t * 16 + (size_t)col] = sum[col];
        }
    }
    return 0;
}

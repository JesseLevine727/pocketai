#ifndef PA_M5_STARTUP_DETAIL_H
#define PA_M5_STARTUP_DETAIL_H
#include <stdint.h>
enum { START_INIT_TOTAL, START_TRANSPOSE, START_SCAN, START_UNITS, START_VALUES,
       START_PROJECT_QUANT, START_PROJECT_GEMM, START_PROJECT_SCALE,
       START_PROJECT_AFFINE, START_PROJECT_RESIDUAL, START_SMOOTH_SETUP,
       START_SMOOTH_SCAN, START_SMOOTH_ROWS, START_PREPARE_TOTAL,
       START_LAZY_INITIAL, START_LAZY_VALUES, START_DETAIL_COUNT };
#if defined(PA_STARTUP_DIAGNOSTIC) && defined(__riscv)
uint64_t pa_startup_begin(void);
void pa_startup_end(uint32_t kind, uint64_t start);
void pa_startup_reset(void);
uint64_t pa_startup_instructions(void);
void pa_startup_leaf_end(uint32_t worker, uint64_t start, uint64_t instructions);
#else
static inline uint64_t pa_startup_begin(void) { return 0; }
static inline void pa_startup_end(uint32_t kind, uint64_t start) { (void)kind; (void)start; }
static inline void pa_startup_reset(void) {}
static inline uint64_t pa_startup_instructions(void) { return 0; }
static inline void pa_startup_leaf_end(uint32_t worker, uint64_t start, uint64_t instructions) {
  (void)worker; (void)start; (void)instructions;
}
#endif
#endif

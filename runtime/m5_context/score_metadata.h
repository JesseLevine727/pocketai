#ifndef PA_M5_CONTEXT_SCORE_METADATA_H
#define PA_M5_CONTEXT_SCORE_METADATA_H
#include <stdint.h>
int pa_context_score_metadata(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch);
#ifdef PA_CONTEXT_COMBINED_SCORES
/* 0: complete tagged scores; 1: exact generic metadata ready for caller fallback;
 * negative: error. No approximate or partially prepared success state. */
int pa_context_score_combined(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch,
    const int32_t *raw, int32_t *tagged);
#endif
#endif

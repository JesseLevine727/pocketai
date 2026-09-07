#ifndef PA_CONTEXT_LOCAL_SCORES_H
#define PA_CONTEXT_LOCAL_SCORES_H
#include <stdint.h>
int pa_context_local_scores(const int32_t *raw, const uint32_t *multipliers,
                            uint32_t length, uint32_t shift, int32_t *tagged);
#ifdef PA_CONTEXT_COMBINED_SCORES
int32_t *pa_context_score_storage(void);
#endif
#endif

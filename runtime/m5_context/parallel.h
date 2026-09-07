#ifndef PA_CONTEXT_PARALLEL_H
#define PA_CONTEXT_PARALLEL_H
#include "pa_m5_hw.h"
typedef void (*pa_context_leaf)(void *, uint32_t, uint32_t, uint32_t);
void pa_context_parallel_bind(pa_m5_hw_context *context);
int pa_context_parallel(pa_context_leaf function, void *argument, uint32_t count);
int pa_context_parallel_execute(pa_m5_hw_shared *shared);
#endif

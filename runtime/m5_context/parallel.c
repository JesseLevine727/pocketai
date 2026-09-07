#include "parallel.h"
#ifdef PA_CONTEXT_PARALLEL_VALUES
#define MINIMUM 32
#else
#define MINIMUM 128
#endif
#if defined(__riscv)
static pa_m5_hw_context *bound;
#define REG(offset) (*(volatile uint32_t *)(UINT32_C(0x12000)+(offset)))
static void fence(void) { __asm__ volatile("fence rw, rw" ::: "memory"); }
void pa_context_parallel_bind(pa_m5_hw_context *context) { bound = context; }
int pa_context_parallel(pa_context_leaf function, void *argument, uint32_t count) {
  if (!bound || count < MINIMUM) { function(argument, 0, count, 0); return 0; }
  pa_m5_hw_shared *shared = bound->shared;
  uint32_t split = (count/2)&~15u;
  uint32_t sequence = shared->request_sequence+1;
  if (!sequence) sequence = 1;
  shared->kind = 3;
  shared->source[0] = (uint32_t)(uintptr_t)function;
  shared->source[1] = (uint32_t)(uintptr_t)argument;
  shared->rows = split; shared->n = count;
  shared->status = -1;
  fence(); shared->request_sequence = sequence; fence(); REG(0) = sequence;
  function(argument, 0, split, 0);
  while (!(REG(8) & 2u)) __asm__ volatile("nop");
  uint32_t returned = REG(4); REG(12) = 2; fence();
  return returned == sequence && shared->completion_sequence == sequence ? shared->status : -1;
}
int pa_context_parallel_execute(pa_m5_hw_shared *shared) {
  if (!shared->source[0] || shared->source[0] >= 0xc000 || (shared->source[0]&1) ||
      !shared->source[1] || !shared->rows || shared->rows >= shared->n || shared->n > 50257)
    return -5;
  pa_context_leaf function = (pa_context_leaf)(uintptr_t)shared->source[0];
  function((void *)(uintptr_t)shared->source[1], shared->rows, shared->n, 1);
  return 0;
}
#else
#ifdef PA_CONTEXT_TEST_THREADS
#include <pthread.h>
typedef struct { pa_context_leaf function; void *argument; uint32_t split, count; } host_job;
static void *host_run(void *opaque) {
  host_job *job = opaque; job->function(job->argument, job->split, job->count, 1); return 0;
}
#endif
void pa_context_parallel_bind(pa_m5_hw_context *context) { (void)context; }
int pa_context_parallel_execute(pa_m5_hw_shared *shared) { (void)shared; return -1; }
int pa_context_parallel(pa_context_leaf function, void *argument, uint32_t count) {
  if (count < MINIMUM) { function(argument, 0, count, 0); return 0; }
  uint32_t split = (count/2)&~15u;
#ifdef PA_CONTEXT_TEST_THREADS
  host_job job = {function, argument, split, count}; pthread_t worker;
  if (pthread_create(&worker, 0, host_run, &job)) return -1;
  function(argument, 0, split, 0);
  return pthread_join(worker, 0) ? -1 : 0;
#else
  function(argument, 0, split, 0); function(argument, split, count, 1); return 0;
#endif
}
#endif

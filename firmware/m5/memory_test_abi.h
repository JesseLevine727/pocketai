#ifndef PA_M5_MEMORY_TEST_ABI_H
#define PA_M5_MEMORY_TEST_ABI_H
#include <stdint.h>
#define M5_TEST_RESULTS 0x0000d000u
#define M5_TEST_WORDS 1024u
struct m5_test_result {
  uint32_t state, errors, traps, last_cause, last_address;
  uint32_t expected_cause, expected_address, last_pc, checksum;
  uint32_t cycle_start, cycle_end, unaligned_cases, branch_cases, reserved[3];
};
#endif

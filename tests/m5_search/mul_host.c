#include "mul_i32.h"
double pa_search_mul_candidate(int32_t value, double scale) {
  return pa_search_mul_i32(value, scale);
}
double pa_search_mul_reference(int32_t value, double scale) {
  return (double)value * scale;
}

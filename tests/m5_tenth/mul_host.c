#include "mul_factor.h"
double pa_tenth_candidate(double lhs, double rhs) {
  pa_tenth_factor factor = pa_tenth_prepare_factor(lhs);
  return pa_tenth_mul_factor(&factor, rhs);
}
double pa_tenth_reference(double lhs, double rhs) { return lhs * rhs; }

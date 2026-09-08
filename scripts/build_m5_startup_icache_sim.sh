#!/usr/bin/env bash
# Fresh production-autonomous (EnableTransfer=1) instruction-cache model.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
STARTUP_SIM=$(realpath -m "${M5_STARTUP_SIM_BUILD:?fresh startup directory}")
if [[ -e "$STARTUP_SIM" || "$(basename "$STARTUP_SIM")" != m5_startup_* ]]; then
  echo 'fresh startup directory required' >&2; exit 1
fi
mkdir -p "$STARTUP_SIM"
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$STARTUP_SIM/sim" --setup pocketai:pa:pa_m5_accelerators \
  >"$STARTUP_SIM/setup.log" 2>&1
touch "$STARTUP_SIM/sim/M5_FAST_TARGET" "$STARTUP_SIM/sim/M5_FAST_PIPELINED" \
  "$STARTUP_SIM/sim/M5_STARTUP_ICACHE"
(cd "$STARTUP_SIM/sim" && bash ./m5_prepare_lsu.sh) >"$STARTUP_SIM/lsu.log" 2>&1
python3 -m scripts.m5_fast_sources "$STARTUP_SIM/sim" --prepare >"$STARTUP_SIM/parent.log"
python3 -m scripts.m5_startup_icache "$STARTUP_SIM/sim" --prepare-export
make -C "$STARTUP_SIM/sim" -j8 >"$STARTUP_SIM/build.log" 2>&1
python3 -m scripts.m5_startup_icache "$STARTUP_SIM/sim" --model >"$STARTUP_SIM/qualification.log"
echo "STARTUP AUTONOMOUS ICACHE MODEL PASS $STARTUP_SIM"

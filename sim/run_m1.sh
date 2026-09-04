#!/usr/bin/env bash
# Complete local M1 verification gate (board/Vivado are separate gates).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash scripts/check_deps.sh all
bash sim/run_shared_bus.sh
bash sim/run_mailbox.sh
bash sim/run_smoke.sh
bash sim/run_cluster.sh
bash scripts/lint_m1.sh

echo "M1 LOCAL PASS"

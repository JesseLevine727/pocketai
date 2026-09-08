#!/usr/bin/env bash
# Fetch immutable candidate macro views. This does not qualify a macro.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:?usage: m6_fetch_sram.sh new_build_m6_directory macro_name}
macro=${2:?macro name required}
case "$output" in build/m6_*) ;; *) echo 'M6 build directory required' >&2; exit 2;; esac
if [[ "$output" == *..* || -e "$output" ]]; then
  echo 'Use a new M6 directory; do not overwrite prior trials' >&2; exit 2
fi
case "$macro" in sram22_512x32m4w8|sram22_1024x32m8w8|sram22_2048x32m8w8) ;;
  *) echo 'macro not reviewed for this preflight' >&2; exit 2;; esac
revision=75cbe961e18ee00d5a6c73fa455505f0bcdf4c05
base="https://raw.githubusercontent.com/ucb-substrate/sram22_sky130_macros/$revision"
mkdir -p "$output"
curl --fail --location --silent --show-error --max-time 60 "$base/LICENSE" -o "$output/LICENSE"
for suffix in .v .lef .gds.gz .spice _tt_025C_1v80.lib _ss_100C_1v60.lib _ff_n40C_1v95.lib; do
  curl --fail --location --silent --show-error --max-time 60 \
    "$base/$macro/$macro$suffix" -o "$output/$macro$suffix"
done
sha256sum "$output"/*

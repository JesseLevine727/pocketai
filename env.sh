# Ibex Verification Toolchain Environment
# Source this file: source ~/pocketai/env.sh

# --- Verilator ---
export VERILATOR_ROOT="$HOME/tools/verilator/root"
export PATH="$HOME/tools/verilator/usr/bin:$PATH"
# The VERILATOR_ROOT ships only the compiled binaries under $VERILATOR_ROOT/bin;
# the runtime Python helpers (verilator_includer, invoked by the generated
# Makefiles) live under usr/share/verilator/bin. Expose them where the Makefiles
# expect them ($(VERILATOR_ROOT)/bin/...). No-op if already present.
if [ -f "$HOME/tools/verilator/usr/share/verilator/bin/verilator_includer" ]; then
  ln -sf "$HOME/tools/verilator/usr/share/verilator/bin/verilator_includer" \
         "$VERILATOR_ROOT/bin/verilator_includer"
fi

# --- FuseSoC ---
export PATH="$HOME/.local/bin:$PATH"

# --- RISC-V 32-bit Bare-metal Toolchain ---
export RISCV="$HOME/tools/riscv"
export PATH="$RISCV/bin:$PATH"

# --- SRecord ---
# The locally unpacked binary needs its matching shared library at runtime.
export POCKETAI_SRECORD_ROOT="$HOME/tools/srecord"
if [ -x "$POCKETAI_SRECORD_ROOT/bin/srec_cat" ]; then
  export PATH="$POCKETAI_SRECORD_ROOT/bin:$PATH"
  export LD_LIBRARY_PATH="$POCKETAI_SRECORD_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# --- Vivado (add path if Vivado is installed) ---
# export VIVADO="/path/to/vivado/2024.1"
# export PATH="$VIVADO/bin:$PATH"

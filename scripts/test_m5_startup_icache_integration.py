"""Reuse qualified memory/M-extension and accelerator harnesses with ICache on."""
import argparse
import json
import re
from pathlib import Path
from scripts.m5_fast_sources import ROOT, pinned, digest
from scripts.m5_startup_icache import required_start, check_export
from scripts.test_m5_startup_icache_probe import run


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--kind', choices=('memory', 'accelerators'), required=True)
    a = p.parse_args(); model = a.model.resolve(); out = a.output.resolve()
    if not out.name.startswith('m5_startup_') or out.exists():
        raise ValueError('fresh startup directory required')
    out.mkdir()
    fetch_mirror = (model/'M5_STARTUP_FETCH').exists()
    if fetch_mirror:
        from scripts.m5_startup_fetch import check as check_fetch
        check_fetch(model)
    else: check_export(model, model=True)
    kit = Path(re.search(r'^VERILATOR_ROOT = (.+)$',
        (model/'Vpa_m5_cluster_top.mk').read_text(), re.M)[1])
    if a.kind == 'memory':
        harness_path = ROOT/'sim/pa_m5_cluster/pa_m5_cluster.cc'
        harness = pinned(harness_path,
            '7afd30921a451a41aaf11f9d4f9481d23b8ca0266e8ba3419b53601cd30fed0e')
        if 'EnableTransfer' in (model/'config.mk').read_text():
            # Original memory harness predates the autonomous mover's sticky
            # cancellation. In that configuration use the qualified supervisor
            # START/reset/flush sequence, keeping every memory assertion.
            h = harness.decode()
            h = h.replace('top.cfg_flush_i = 0; top.memory_abort_i = 1;',
                          'top.cfg_flush_i = 0; top.memory_abort_i = 0;')
            h = h.replace('top.IO_RST_N = 0; top.CORE_RST_N = 0;',
                          'top.IO_RST_N = 0; top.CORE_RST_N = 0; top.memory_abort_i = 1;')
            old = '    top.memory_abort_i = 0; tick(); top.CORE_RST_N = 1; tick();'
            if h.count(old) != 1: raise ValueError('ambiguous memory START')
            h = h.replace(old, '''    require(top.memory_quiesced_o && !top.CORE_RST_N, "start before drain");
    require(top.awready_o && top.arready_o && !top.awvalid_i && !top.arvalid_i &&
            !top.wvalid_i && !top.bvalid_o && !top.rvalid_o, "host not retired before reset");
    top.IO_RST_N = 0; top.memory_abort_i = 0;
    for (unsigned i=0; i<4; ++i) tick();
    top.cfg_flush_i = 1; top.IO_RST_N = 1; tick();
    wait_for([&] { return top.flush_ready_o; }, 100, "supervisor START flush");
    top.cfg_flush_i = 0; tick();
    require(!top.transfer_cancel_o && !top.memory_poisoned_o && !top.memory_busy_o,
            "START retained cancellation or traffic");
    top.CORE_RST_N = 1; tick();''')
            harness = h.encode()
        firmware = pinned(ROOT/'firmware/m5_fast/arithmetic_test.c',
            'e37073d75a70e530ddbba9691ddf25b21893a4b6e8db83cf1e93c74ba31c8a6d').decode()
        pinned(ROOT/'firmware/m5/memory_test.c',
            'cfe6aff469989d88c6f45886f6e351e568f3ffa52b5d3d179e380a3513c47544')
        firmware = firmware.replace('"../m5/memory_test.c"', '"'+str(ROOT/'firmware/m5/memory_test.c')+'"')
        # Extra tests run before, and do not alter, any of the inherited cases.
        firmware = firmware.replace('void m5_memory_main(uint32_t hart) {', '''void m5_memory_main(uint32_t hart) {
  volatile uint32_t *code = (volatile uint32_t *)(0x40000000u + (hart << 12));
  uint32_t (*function)(uint32_t) = (uint32_t (*)(uint32_t))code;
  uint32_t enabled;
  __asm__ volatile("csrr %0, 0x7c0" : "=r"(enabled));
  check(hart, (enabled & 1) == EXPECTED_CACHE, 0x80000);
  code[0] = 0x00750513u; code[1] = 0x00008067u;
  __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
  check(hart, function(100 + hart) == 107 + hart, 0x100000);
  code[0] = 0x00b50513u;
  __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
  check(hart, function(100 + hart) == 111 + hart, 0x200000);
''').replace('EXPECTED_CACHE', '0' if fetch_mirror else '1')
        if fetch_mirror:
            # The original trap skips explicitly faulting data instructions.
            # Add one precise instruction-port fault with an explicit resume PC;
            # restore its pre-test counters before the inherited three faults.
            original_memory = pinned(ROOT/'firmware/m5/memory_test.c',
                'cfe6aff469989d88c6f45886f6e351e568f3ffa52b5d3d179e380a3513c47544').decode()
            original_memory = original_memory.replace('  pc += 4;',
                '  pc = cause == 1 && result[hart].reserved[2] ? result[hart].reserved[2] : pc + 4;')
            firmware = firmware.replace('#include "'+str(ROOT/'firmware/m5/memory_test.c')+'"', original_memory)
            marker = '  static const uint32_t edges[] ='
            if firmware.count(marker) != 1: raise ValueError('arithmetic entry changed')
            firmware = firmware.replace(marker, '''  // A real non-RAM local instruction read: the per-hart mailbox holds RET.
  // This exercises fallback DATA, not just an unmapped-address error response.
  volatile uint32_t *mail_code = (volatile uint32_t *)(0x12000u + 4u*hart);
  *mail_code = 0x00008067u;
  __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
  check(hart, ((uint32_t (*)(uint32_t))mail_code)(700u+hart) == 700u+hart, 0x4000000);
  *(volatile uint32_t *)0x1200cu = 1u << hart;
  const uint32_t invalid_instruction_addresses[] = {0x40003000u, 0x00010000u};
  for (uint32_t fault=0; fault<2; ++fault) {
  result[hart].expected_cause = 1;
  result[hart].expected_address = invalid_instruction_addresses[fault];
  uint32_t resume;
  __asm__ volatile(".option push\\n.option norvc\\nla %0, 1f\\nsw %0, 0(%1)\\njalr zero,0(%2)\\n1:\\n.option pop"
      : "=&r"(resume) : "r"(&result[hart].reserved[2]), "r"(invalid_instruction_addresses[fault]) : "memory");
  check(hart, result[hart].traps == 1 && result[hart].last_cause == 1 &&
              result[hart].last_address == invalid_instruction_addresses[fault], 0x2000000);
  result[hart].reserved[2] = 0; result[hart].traps = 0;
  }
  // Local RAM aliases across the image: full-word and byte-store coherence.
  // Test firmware occupies less than 8 KiB; these locations are spare test RAM.
  for (uint32_t slot=1; slot<=6; ++slot) {
    uint32_t address = (slot == 6 ? 0xb000u : slot*0x2000u) + hart*0x100u;
    volatile uint32_t *local_code = (volatile uint32_t *)address;
    uint32_t (*local_function)(uint32_t) = (uint32_t (*)(uint32_t))address;
    local_code[0] = 0x00750513u; local_code[1] = 0x00008067u;
    __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
    check(hart, local_function(100 + hart) == 107 + hart, 0x400000);
    ((volatile uint8_t *)local_code)[2] = 0xb5u;
    __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
    check(hart, local_function(100 + hart) == 111 + hart, 0x800000);
    check(hart, local_code[0] == 0x00b50513u &&
                ((volatile uint16_t *)local_code)[1] == 0x00b5u &&
                ((volatile uint8_t *)local_code)[2] == 0xb5u, 0x4000000);
    ((volatile uint16_t *)local_code)[1] = 0x00d5u;
    __asm__ volatile("fence rw,rw\\n.word 0x0000100f" ::: "memory");
    check(hart, local_code[0] == 0x00d50513u &&
                local_function(100 + hart) == 113 + hart, 0x8000000);
    result[hart].reserved[1] += 2;
  }
  check(hart, result[hart].reserved[1] == 12, 0x1000000);
'''+marker)
            h = harness.decode().replace('result[12] == 1,', 'result[12] == 1 && result[14] == 12,')
            harness = h.encode()
    else:
        harness_path = ROOT/'sim/pa_m5_cluster/pa_m5_accelerators.cc'
        harness = pinned(harness_path,
            '44ada67c352b0c88f33549dc3601dd5e1b0807d5e7bcc0e85c70b8765d01a8c6')
        firmware = pinned(ROOT/'firmware/m5/accelerator_test.c',
            'c3e112c37be573457062a708fa8632dfc4287330b7e994404cc3f83ff1726a3e').decode()
    (out/'test.cc').write_bytes(harness)
    (out/'test.c').write_text(firmware)
    boot = required_start() if not fetch_mirror else pinned(ROOT/'firmware/m5/memory_test_start.S',
        '52765bdb2a6e093068b9258f3bce9c0681c85a200c0c6a04b5641f776dc3fd4b').decode()
    (out/'start.S').write_text(boot)
    run(['riscv64-unknown-elf-gcc', '-march=rv32imc_zicsr', '-mabi=ilp32',
         '-O2', '-fno-fast-math', '-msmall-data-limit=0', '-mno-relax',
         '-Wall', '-Wextra', '-Werror', '-nostdlib', '-ffreestanding', '-fno-builtin',
         '-Wl,--fatal-warnings', '-T', 'firmware/m5/memory_test.ld',
         '-Iruntime/m5', '-Ifirmware/m5', out/'start.S', out/'test.c', '-lgcc',
         '-o', out/'test.elf'], out/'firmware.log')
    if fetch_mirror and a.kind == 'memory':
        import subprocess
        symbols = subprocess.check_output(['riscv64-unknown-elf-nm', str(out/'test.elf')], text=True)
        end = int(re.search(r'^([0-9a-f]+) \w _bss_end$', symbols, re.M)[1], 16)
        if end > 0x2000: raise ValueError('test program overlaps directed local code probes')
    run(['riscv64-unknown-elf-objcopy', '-O', 'binary', '--gap-fill', '0',
         '--pad-to', '65536', out/'test.elf', out/'test.bin'], out/'objcopy.log')
    run(['g++', '-O2', '-std=c++17', '-pthread', '-I'+str(model),
         '-I'+str(kit/'include'), '-I'+str(kit/'include/vltstd'),
         out/'test.cc', model/'Vpa_m5_cluster_top__ALL.a', model/'verilated.o',
         model/'verilated_threads.o', '-latomic', '-o', out/'test'], out/'link.log')
    (out/'manifest.json').write_text(json.dumps(dict(schema=1, kind=a.kind, fetch_mirror=fetch_mirror,
        inputs={str(x.relative_to(ROOT)): digest(x.read_bytes()) for x in
                [harness_path, model/'Vpa_m5_cluster_top__ALL.a']},
        generated={x.name: digest(x.read_bytes()) for x in out.iterdir() if x.is_file()}),
        indent=2)+'\n')
    run(['stdbuf', '-oL', out/'test', out/'test.bin'], out/'test.log', cwd=model, timeout=120)
    if a.kind == 'accelerators':
        run(['env', 'PA_M5_AXI_DELAY=7', 'stdbuf', '-oL', out/'test', out/'test.bin'],
            out/'delayed.log', cwd=model, timeout=120)
    print((out/'test.log').read_text())
    print('STARTUP '+('FETCH MIRROR' if fetch_mirror else 'ICACHE')+' INTEGRATION PASS', a.kind, out)


if __name__ == '__main__': main()

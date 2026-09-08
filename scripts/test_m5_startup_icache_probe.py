"""Short matched cache-off/on probe, reusing an immutable compiled RTL model."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from scripts.m5_startup_icache import start
from scripts.m5_fast_sources import ROOT, pinned, digest


def run(command, output, cwd=ROOT, timeout=60):
    with output.open('w') as stream:
        subprocess.run([str(x) for x in command], cwd=cwd, stdout=stream,
                       stderr=subprocess.STDOUT, check=True, timeout=timeout)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plain', action='store_true', help='two cache-off runs on the qualified baseline model')
    a = p.parse_args()
    model, out = a.model.resolve(), a.output.resolve()
    fetch_mirror = (model/'M5_STARTUP_FETCH').exists()
    if fetch_mirror:
        from scripts.m5_startup_fetch import check as check_fetch
        check_fetch(model)
    elif a.plain:
        from scripts.m5_fast_sources import check as check_fast
        if not (model/'M5_FAST_PIPELINED').exists():
            raise ValueError('matched baseline must use qualified pipelined fast multiplier')
        check_fast(model, model=True)
    if not out.name.startswith('m5_startup_') or out.exists():
        raise ValueError('fresh startup output required')
    out.mkdir()
    original = pinned(ROOT/'sim/pa_m5_cluster/pa_m5_numerics.cc',
        'f94342e9c5a0921eab6b387892bc8c1def6d24e069824dbad2980dbad195d85e').decode()
    probe = ROOT/'runtime/m5_startup/icache_probe.c'
    metadata = ROOT/'runtime/m5_opt/pa_m5_metadata_opt.c'
    run(['gcc', '-O2', '-fno-fast-math', '-DSTARTUP_PROBE_HOST', '-Iruntime/m5',
         probe, metadata, '-o', out/'oracle'], out/'host_build.log')
    run([out/'oracle'], out/'expected.json')
    expected = json.loads((out/'expected.json').read_text())
    lo, hi = original.index('  void complete_numerics()'), original.index('  template <typename Condition>')
    harness = original[:lo] + '''  void complete_probe(unsigned enabled) {
    // Console done is sticky until IO reset. Poll fresh image-owned state so
    // the reset/reload check cannot mistake the preceding run for completion.
    unsigned elapsed = 0;
    while (read_ram(0xd000u) != 3u) {
      require(elapsed++ < 8000, "bounded probe completion");
      for (unsigned i=0; i<1000; ++i) tick();
    }
    require(top.software_done_o, "missing done latch");
    stop_and_drain();
    const uint32_t expected[2] = {EXPECTED0u, EXPECTED1u};
    for (unsigned hart = 0; hart < 2; ++hart) {
      std::array<uint32_t, 16> r{};
      for (unsigned i=0; i<16; ++i) r[i] = read_ram(0xd000u + hart*64u + i*4u);
      std::printf("CACHE_PROBE cache=%u hart=%u hash=%08x cycles=%u instructions=%u state=%u errors=%u cause=%u pc=%08x\\n",
                  r[3], hart, r[2], r[5]-r[4], r[6], r[0], r[1], r[7], r[9]);
      require(r[0] == (hart ? 2u : 3u) && !r[1] && r[2] == expected[hart] &&
              r[3] == enabled && r[5] > r[4] && r[6] > 0 && !r[7], "probe mismatch");
    }
  }
''' .replace('EXPECTED0', str(expected[0])).replace('EXPECTED1', str(expected[1])) + original[hi:]
    main_at = harness.index('int main(')
    harness = harness[:main_at] + '''int main(int argc, char **argv) {
  try {
    require(argc == 3, "usage: probe cache_off.bin cache_on.bin");
    Simulation sim(argc, argv);
    // Reprogram under core reset without IO reset: exercise invalidation and
    // stale instruction rejection across actual whole-image reloads.
    for (unsigned mode : {0u, 1u, 0u, 1u}) {
      std::ifstream source(argv[mode+1], std::ios::binary);
      require(bool(source), "image missing");
      std::vector<uint8_t> image((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
      sim.configure(false); sim.load(image); sim.start(); sim.complete_probe(mode);
    }
    std::puts("STARTUP CACHE PROBE EXACT / RESET-RELOAD PASS");
    sim.top.final(); return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "STARTUP CACHE PROBE FAIL: %s\\n", error.what()); return 1;
  }
}
'''
    if fetch_mirror or a.plain:
        # Two independently reset repeats of the no-I-cache coherent mirror.
        # Do not label these as cache-off/on or infer GPT-2 throughput.
        harness = harness.replace('{0u, 1u, 0u, 1u}', '{0u, 0u}')
        harness = harness.replace('STARTUP CACHE PROBE', 'STARTUP FETCH MIRROR PROBE' if fetch_mirror else 'STARTUP BASELINE PROBE')
        harness = harness.replace('top.cfg_flush_i = 0; top.memory_abort_i = 1;',
                                  'top.cfg_flush_i = 0; top.memory_abort_i = 0;')
        harness = harness.replace('top.IO_RST_N = 0; top.CORE_RST_N = 0;',
                                  'top.IO_RST_N = 0; top.CORE_RST_N = 0; top.memory_abort_i = 1;')
        harness = harness.replace('    top.memory_abort_i = 0; tick(); top.CORE_RST_N = 1; tick();', '''
    require(top.memory_quiesced_o && !top.CORE_RST_N, "START before drain");
    top.IO_RST_N = 0; top.memory_abort_i = 0;
    for (unsigned i=0; i<4; ++i) tick();
    top.cfg_flush_i = 1; top.IO_RST_N = 1; tick();
    wait_for([&] { return top.flush_ready_o; }, 100, "START flush");
    top.cfg_flush_i = 0; tick(); top.CORE_RST_N = 1; tick();''')
    (out/'probe.cc').write_text(harness)
    (out/'start.S').write_text(start())
    for mode in (0, 1):
        elf = out/f'cache_{mode}.elf'
        run(['riscv64-unknown-elf-gcc', '-march=rv32imc_zicsr', '-mabi=ilp32',
             '-O2', '-fno-fast-math', f'-DSTARTUP_ICACHE_ENABLE={mode}',
             '-msmall-data-limit=0', '-mno-relax', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-ffreestanding', '-fno-builtin', '-Wl,--fatal-warnings',
             '-T', 'firmware/m5/memory_test.ld', '-Iruntime/m5', out/'start.S',
             probe, metadata, '-lgcc', '-o', elf], out/f'build_{mode}.log')
        run(['riscv64-unknown-elf-objcopy', '-O', 'binary', '--gap-fill', '0',
             '--pad-to', '65536', elf, out/f'cache_{mode}.bin'], out/f'objcopy_{mode}.log')
    # Link new harness against existing Verilated RTL archive, without modifying
    # that earlier experiment or recompiling its model.
    kit = Path(re.search(r'^VERILATOR_ROOT = (.+)$',
        (model/'Vpa_m5_cluster_top.mk').read_text(), re.M)[1])
    run(['g++', '-O2', '-std=c++17', '-pthread', '-I'+str(model),
         '-I'+str(kit/'include'), '-I'+str(kit/'include/vltstd'),
         out/'probe.cc', model/'Vpa_m5_cluster_top__ALL.a', model/'verilated.o',
         model/'verilated_threads.o', '-latomic', '-o', out/'probe'], out/'link.log')
    identity = (model/'startup_fetch_sources.json' if fetch_mirror else
                model/'M5_FAST_PIPELINED' if a.plain else model.parent/'icache_derivation.json')
    manifest = dict(schema=1, expected_hashes=expected, fetch_mirror=fetch_mirror,
        scope='bounded local/soft-f64 probe, not model throughput',
        inputs={str(x.relative_to(ROOT)): digest(x.read_bytes()) for x in
                [probe, metadata, model/'Vpa_m5_cluster_top__ALL.a',
                 identity]},
        generated={x.name: digest(x.read_bytes()) for x in out.iterdir() if x.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    run(['stdbuf', '-oL', out/'probe', out/'cache_0.bin', out/'cache_1.bin'],
        out/'probe.log', cwd=model, timeout=90)
    print((out/'probe.log').read_text())


if __name__ == '__main__':
    main()

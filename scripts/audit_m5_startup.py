"""Read-only startup measurement checks; collection never implies closure by itself."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from scripts.m5_sweep_policy import ROOT, sha
from scripts.audit_m5_sweep import require, finite_positive
from scripts.audit_m5_context import stats


def read(path):
    return json.loads((ROOT/path).read_text())


def validate_campaign(report, refs):
    p = report['policy']
    require(report['status'] == refs['status'] == 'PASS' and report['within_budget'] and
            0 < report['elapsed_seconds'] <= 3600 and p['board_budget_seconds'] == 3600 and
            p['cleanup_reserve_seconds'] == 120, 'campaign/budget gate')
    require(report['clock_hz'] == p['clock_hz'] == 91000000 and
            report['allocated_bytes'] == 266289152, 'clock/arena changed')
    require(report['normal_unload'] and not report.get('cleanup_error') and
            report['dma_after_return']['owner'] == 0 and
            all(report['info_after_close_reopen'][k] == 0 for k in ('owner', 'allocated_pages', 'pte_dma')),
            'normal ownership/page/PTE release missing')
    require(report['policy_sha256'] == refs['policy_sha256'], 'oracle/policy mismatch')
    require(all(report['sha256'][name] == value for name, value in p['pinned'].items()),
            'executed file differs from frozen policy')
    reject = report['boundary_rejection']
    require(reject['state'] == 5 and reject['error'] == 1 and reject['cache_valid'] == 17 and
            reject['generated_count'] == 19 and reject['output_sentinel_unchanged'] and
            set(reject['cache_regions_unchanged']) == {'k', 'v', 'k8', 'kunits'} and
            reject['recovery'] == 'subsequent accepted runs', 'overflow non-mutation/recovery missing')
    require([i['trial'] for i in report['trials']] == p['matrix'], 'missing/reordered trials')
    previous = None
    for item in report['trials']:
        t, r = item['trial'], item['result']
        require(item['status'] == 'PASS' and not item['bound_exceeded'] and
                0 < item['case_elapsed_seconds'] <= t['bound_seconds'] and
                item['started_campaign_seconds'] >= 0 and
                item['started_campaign_seconds']+t['bound_seconds']+120 <= 3600,
                'trial/bounded admission gate')
        if t['kind'] == 'cached':
            seed = refs['seeds'][str(t['past'])]
            expected = seed['expected']
            tokens = seed.get('prefill_tokens', [seed.get('input_token')])
            require(r['status'] == 'PASS' and r['initial_past'] == t['past'] and
                    r['input_tokens'] == tokens and r['cache_valid'] == t['past']+len(tokens) and
                    r['token'] == expected['token'] and
                    r['firmware_sha256'] == p['pinned']['m5_profile.bin'], 'cached identity/input/output')
            require(r['context_role'] == seed['context_role'], 'cached request boundary changed')
            if r['context_role'] == 'warm_last_slot':
                require(previous is not None and previous['cache_valid'] == seed['past'] and
                        previous['token'] == seed['input_token'] and
                        previous['kv_sha256'] == seed['prefill_kv_sha256'], 'hidden/future/unmatched warm state')
                require(r['derived_cache']['appended_vectors'] == 288 and
                        r['derived_cache']['updated_columns'] >= previous['derived_cache']['updated_columns'],
                        'warm state was reset')
            else:
                require(r['derived_cache']['appended_vectors'] == 144*len(tokens), 'cold/prefill row coverage')
            require(r['derived_cache']['cold_heads'] == 144, 'incomplete head coverage')
            model, delivered = r['model_seconds'], r['host_request_through_delivery_seconds']
            require(model == r['model_cycles']/91000000 and r['profile_enabled'] == t['profile'],
                    'cycle/profile boundary changed')
            require(r['workspace_high_water'] <= 2609152, 'workspace bound exceeded')
            if t['profile']:
                phases = r['phases']
                order = [(1, 0)]+[(kind, layer) for layer in range(12) for kind in range(2, 10)]
                order += [(10, 0), (11, 0), (12, 0)]
                require([(x['kind'], x['layer']) for x in phases] == order, 'phase coverage')
                for x in phases:
                    require(0 <= x['gemm_cycles']+x['sfpu_cycles'] <= x['service_cycles'] <= x['cycles'] and
                            x['cpu_remainder_cycles'] == x['cycles']-x['service_cycles'], 'nested phase accounting')
                require(sum(x['cycles'] for x in phases)+r['unassigned_profile_tail_cycles'] ==
                        r['model_cycles'], 'missing model cycles')
                for counter, seconds in (('service_cycles', 'service_seconds'),
                        ('gemm_cycles', 'gemm_compute_seconds'), ('sfpu_cycles', 'sfpu_compute_seconds')):
                    require(sum(x[counter] for x in phases)/91000000 == r[seconds], 'nested service totals')
                require(math.isclose(r['service_seconds']+r['cpu_remainder_seconds'], model, abs_tol=1e-9),
                        'model/service sum')
                details = r['startup_detail']
                require(all(x['seconds'] == x['cycles']/91000000 for x in details), 'detail cycle conversion')
                if r['derived_cache'].get('version', 1) == 2:
                    require(len(details) == 16, 'missing deferred first-use counters')
                    cold = r['context_role'] != 'warm_last_slot'
                    for index, count in {0: 144 if cold else 0, 13: 12,
                                         14: 144 if cold else 0, 15: 144*len(tokens)}.items():
                        require(details[index]['calls'] == count, 'first-use coverage')
                    required = details[13]['seconds']+details[14]['seconds']
                    require(r['initial_required_derived_seconds'] == required and 0 <= required <= model and
                            details[14]['cycles'] <= details[15]['cycles'], 'hidden first-demand work')
            else:
                require(not r['phases'] and r['service_seconds'] is None and
                        'startup_detail' not in r, 'profile contaminated plain sample')
            previous = r
        else:
            require(t['kind'] == 'full', 'unknown trial type')
            case = refs['cases'][t['case']]
            count = t['new_tokens']; expected = case['steps'][count-1]
            require(r['id'] == case['id'] and r['prompt_tokens'] == case['input_tokens'] and
                    r['generated_tokens'] == [x['token'] for x in case['steps'][:count]] and
                    r['cache_valid'] == len(case['input_tokens'])+count-1, 'original request changed')
            image = 'm5_trace.bin' if t['capture'] else 'm5_runtime.bin'
            require(r['execution_image'] == image and r['firmware_sha256'] == p['pinned'][image],
                    'full request image changed')
            if t['capture']:
                baseline = read('build/m5_startup_split_fixed_diag_v1/campaign.json')
                expected_trace = next(x['result']['traces'] for x in baseline['trials']
                                      if x['trial'].get('capture'))
                require(r['traces'] == expected_trace, 'original story tensors changed')
            model, delivered = r['firmware_seconds'], r['request_through_delivery_seconds']
            require(len(r['decode_seconds']) == count-1 and
                    math.isclose(r['ttft_seconds']+sum(r['decode_seconds']), model, abs_tol=.001) and
                    r['request_tokens_per_second'] == count/delivered, 'full-request accounting')
            require(r['work_high_water'] <= 2609152, 'full request workspace bound')
            previous = None
        require(finite_positive(model) and finite_positive(delivered) and
                model < delivered <= item['case_elapsed_seconds'], 'invalid delivery interval')
        require(r['logits_sha256'] == expected['logits_sha256'] and
                r['kv_sha256'] == expected['cache_sha256'], 'all logits/complete valid KV mismatch')


def validate_final(reports, references, selection, binaries, overlay):
    """Every selected repetition must pass; averages cannot conceal a miss."""
    all_full = []
    for prefix in ('story', 'science'):
        key = selection['final_'+prefix]
        report = reports[key]; refs = references[key]
        require(refs['case'] == prefix, 'independent prefix changed')
        pinned = report['policy']['pinned']
        require(all(pinned[n] == overlay[n] for n in overlay), 'final hardware identity')
        require(all(pinned[n] == binaries[n] for n in ('m5_runtime.bin', 'm5_profile.bin', 'm5_trace.bin')),
                'final firmware identity')
        for past, limit in ((1022, 20.0), (1023, 10.0)):
            group = [x for x in report['trials'] if x['trial'].get('past') == past]
            require(len(group) >= 3 and all(not x['trial']['profile'] and
                    x['result']['derived_cache'].get('version') == 2 and
                    x['result']['host_request_through_delivery_seconds'] <= limit for x in group),
                    'cold/warm repeated per-sample performance gate')
        all_full += [x for x in report['trials'] if x['trial']['kind'] == 'full']
        diagnostic = reports[selection['diagnostic_'+prefix]]
        require(references[selection['diagnostic_'+prefix]]['case'] == prefix, 'diagnostic prefix')
        require(diagnostic['policy']['pinned']['m5_profile.bin'] == binaries['m5_detail.bin'] and
                all(diagnostic['policy']['pinned'][n] == overlay[n] for n in overlay), 'diagnostic image')
        cold = [x for x in diagnostic['trials'] if x['trial'].get('past') == 1022]
        require(cold and all(x['trial']['profile'] and
                x['result']['initial_required_derived_seconds'] <= 10.0 and
                x['result']['host_request_through_delivery_seconds'] <= 20.0 for x in cold),
                'cold initialization diagnostic gate')
    for name, tokens, seconds in (('science', 1, 10.0), ('computing', 1, 10.0), ('story', 2, 20.0)):
        group = [x for x in all_full if x['trial']['case'] == name and not x['trial']['capture']]
        require(len(group) >= 3 and all(x['trial']['new_tokens'] == tokens and
                x['result']['request_through_delivery_seconds'] <= seconds for x in group),
                'original short-request repeated performance gate: '+name)
    require(any(x['trial']['case'] == 'story' and x['trial']['capture'] for x in all_full),
            'final original physical story trace missing')


def validate_stage(stage):
    stage = Path(stage)
    report, refs = read(stage/'campaign.json'), read(stage/'references/manifest.json')
    validate_campaign(report, refs)
    validate_references(refs)
    layout = Path('build/m5_arena.1Org4t/model/layout.json')
    require(report['sha256']['model.bin'] == read(layout)['model_sha256'] and
            report['sha256']['layout.json'] == sha(ROOT/layout), 'complete model/layout identity changed')
    require(report['policy'] == read(stage/'policy.json') and
            report['policy_sha256'] == sha(ROOT/stage/'policy.json') and
            report['reference_manifest_sha256'] == sha(ROOT/stage/'references/manifest.json'),
            'measured policy/reference binding')
    for name, digest in report['policy']['pinned'].items():
        path = ROOT/stage/'deployed'/name if name.endswith('.py') else ROOT/report['policy']['source_paths'][name]
        require(sha(path) == digest, 'historical deployed artifact changed: '+str(path))
    return report, refs


def validate_references(refs):
    require(refs['case'] in ('story', 'science'), 'unknown independent prefix')
    directory = 'build/m5_context_'+refs['case']+'_reference_v'+('2' if refs['case'] == 'story' else '1')
    canonical = read(directory+'/manifest.json')
    for past in ('1022', '1023'):
        require(refs['seeds'][past] == canonical['seeds'][past], 'independent maximum-context oracle changed')
    fixtures = {x['id']: x for x in read('build/m4_runtime_fixtures/manifest.json')['generation']}
    require(refs['cases'] == fixtures, 'original full-request oracles changed')
    prompt = refs['seeds']['0']
    require(any(prompt['prefill_tokens'] == case['input_tokens'] and prompt['expected'] == case['steps'][0]
                for case in fixtures.values()), 'actual prefill oracle changed')


def hardware_from_reports(directory, reset_count=9, data_read_mirror=False):
    def text(name): return (ROOT/directory/'reports'/name).read_text()
    timing = text('m5_timing_summary.rpt')
    m = re.search(r'WNS\(ns\).*?\n\s*-+[^\n]*\n\s*([^\n]+)', timing, re.S)
    require(m, 'missing timing summary')
    v = m[1].split()
    result = dict(wns_ns=float(v[0]), tns_ns=float(v[1]), hold_ns=float(v[4]), ths_ns=float(v[5]), clock_mhz=91)
    require('10.989          91.000' in timing and
            len(set(re.findall(r'\d+\. checking \w+ \(0\)', timing))) == 12 and
            'All user specified timing constraints are met.' in timing, 'timing constraints incomplete')
    route = text('m5_route_status.rpt')
    counts = [int(re.search(label+r'\.+\s*:\s*(\d+)', route)[1]) for label in
              ('# of routable nets', '# of fully routed nets', '# of nets with routing errors')]
    require(counts[0] == counts[1] and counts[0] > 0 and counts[2] == 0, 'incomplete routing')
    result['routed_nets'] = counts[0]
    utilization = text('m5_utilization.rpt')
    for key, label in (('luts', 'Slice LUTs'), ('registers', 'Slice Registers'),
                       ('bram36', 'Block RAM Tile'), ('dsp', 'DSPs'), ('slices', 'Slice')):
        found = re.search(r'\|\s*'+label+r'\s*\|\s*([\d.]+)\s*\|', utilization)
        require(found, 'missing utilization '+label); result[key] = float(found[1])
    for name, rule, count in (('m5_drc.rpt', 'RTSTAT-10', 1), ('m5_methodology.rpt', 'LUTAR-1', reset_count)):
        rules = re.findall(r'^\|\s*([A-Z][A-Z0-9-]+)\s*\|\s*(Warning|Error|Critical Warning)\s*\|[^\n]+?\|\s*(\d+)\s*\|', text(name), re.M)
        require(rules == [(rule, 'Warning', str(count))], 'unreviewed DRC/methodology finding')
    require(result['wns_ns'] >= .250 and result['tns_ns'] == 0 and result['hold_ns'] > 0 and
            result['ths_ns'] == 0 and result['dsp'] == 0 and
            result['bram36'] == (127.5 if data_read_mirror else 111.5),
            'hardware timing/resource gate')
    config = text('m5_fast_synth_configuration.rpt')
    for hart in (0, 1):
        require(f'hart={hart} multiplier=RV32MFast cells=91' in config, 'two fast harts not proven')
    require('fetch_mirror_bytes=65536 bram36=16 bram18=0' in config, 'unexpected instruction mirror')
    if data_read_mirror:
        require('data_read_mirror_bytes=65536 bram36=16 bram18=0' in config,
                'dedicated data-read bank not proven')
    for name in ('m5_pynq.bit', 'm5_pynq.hwh', 'm5_pynq_final.dcp'):
        require((ROOT/directory/name).is_file(), 'no qualified final '+name)
    return result


def manifest_paths():
    sources = set()
    for pattern in ('runtime/m5_startup/*', 'scripts/*m5_startup*', 'zynq/*m5_startup*',
                    'tests/m5_startup/*', 'docs/M5_STARTUP*.md'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    artifacts = set()
    for directory in ROOT.glob('build/m5_startup_*'):
        entries = directory.rglob('*') if directory.is_dir() else (directory,)
        for p in entries:
            # Historical stage symlinks can target current Python sources.
            # Archive actual deployed files instead; canonical immutable binary
            # targets and each policy's exact identity are checked separately.
            if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts:
                artifacts.add(str(p.relative_to(ROOT)))
    return sources, artifacts


def summarize(reports):
    result = {}
    for name, report in reports.items():
        r = dict(status=report['status'], elapsed_seconds=report['elapsed_seconds'], cached={}, full=[])
        for role in ('cold_initialization_in_model', 'warm_last_slot', 'actual_prompt_prefill'):
            samples = [x['result'] for x in report['trials'] if x['trial']['kind'] == 'cached' and
                       x['result']['context_role'] == role]
            if samples:
                r['cached'][role] = dict(delivered=stats([x['host_request_through_delivery_seconds'] for x in samples]),
                    model=stats([x['model_seconds'] for x in samples]),
                    initial_required_seconds=[x['initial_required_derived_seconds'] for x in samples
                                              if 'initial_required_derived_seconds' in x])
        for item in report['trials']:
            t, x = item['trial'], item['result']
            if t['kind'] == 'full':
                r['full'].append(dict(id=t['id'], case=t['case'], output_tokens=t['new_tokens'],
                    trace=t['capture'], model_seconds=x['firmware_seconds'],
                    delivered_seconds=x['request_through_delivery_seconds'],
                    delivered_output_tokens_per_second=t['new_tokens']/x['request_through_delivery_seconds']))
        result[name] = r
    return result


NATIVE = {'attention_test.log': 'M5 SCALAR ATTENTION LAYOUT EXACT PASS 15',
    'native_test.log': 'M5 NUMERICAL FOUNDATION PASS',
    'ready_test.log': 'STARTUP LAZY CONTRACT PASS 32',
    'combined_test.log': 'CONTEXT COMBINED SCORES EXACT PASS 84',
    'ops_test.log': 'STARTUP GENERIC SCALAR EXACT PASS 96',
    'bounded_test.log': 'STARTUP BOUNDED PRODUCT EXACT PASS 462147',
    'word_test.log': 'STARTUP WORD AFFINE EXACT PASS 300000',
    'project_test.log': 'STARTUP FUSED PROJECT EXACT PASS 1776 accepted rows; 1686 fallback',
    'product_test.log': 'STARTUP PRODUCT TWO-ROUNDING EXACT PASS 330000',
    'batch_test.log': 'STARTUP BATCH EXACT PASS 20 accepted; 120 rejections',
    'fixed_test.log': 'STARTUP FIXED FACTOR EXACT PASS 500000'}


def validate(evidence, files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS' and not evidence['m6_started'],
            'startup goal not qualified')
    s = evidence['selection']
    for name, report in evidence['reports'].items():
        validate_campaign(report, evidence['references'][name])
    require(evidence['summary'] == summarize(evidence['reports']), 'changed/omitted summary samples')
    validate_final(evidence['reports'], evidence['references'], s, evidence['binaries'], evidence['overlay'])
    if not files: return
    require(evidence['baseline_evidence_sha256'] == sha(ROOT/'docs/m5_context_evidence.json'), 'prior closure changed')
    reset_count = s['reviewed_reset_count']
    data_read_mirror = s.get('data_read_mirror', False)
    require(evidence['hardware'] == hardware_from_reports(s['hardware'], reset_count, data_read_mirror),
            'hardware summary changed')
    for name, digest in evidence['overlay'].items():
        require(sha(ROOT/s['hardware']/name) == digest, 'qualified overlay changed')
    for name, digest in evidence['binaries'].items():
        require(sha(ROOT/s['firmware']/name) == sha(ROOT/s['repro']/name) == digest,
                'fresh firmware reproduction mismatch')
        require((ROOT/s['firmware']/name).stat().st_size == 65536, 'local RAM image size changed')
    for directory in (s['firmware'], s['repro']):
        stacks = read(Path(directory)/'stack_bound_v2.json')
        require({x['kind'] for x in stacks} == {'runtime', 'profile', 'detail', 'trace'}, 'missing stack image')
        for x in stacks:
            require(0 < x['shared_per_hart_bound_bytes'] <= x['limit_bytes'] == 4096 and
                    x['elf_sha256'] == sha(ROOT/directory/('m5_'+x['kind']+'.elf')) and
                    x['firmware_sha256'] == evidence['binaries']['m5_'+x['kind']+'.bin'], 'stack/binary mismatch')
        for name, marker in NATIVE.items():
            require(marker in (ROOT/directory/name).read_text(), 'missing native gate '+name)
        derivation = read(Path(directory)/'generated/startup_derivation.json')
        if derivation['variant'] in ('bias_reuse', 'residual_fixed'):
            require('STARTUP BIAS REUSE EXACT PASS 1024 sequences; 2048 reused rows; 3168 fallbacks'
                    in (ROOT/directory/'bias_reuse_test.log').read_text(),
                    'missing exact multirow bias reuse/lifetime gate')
        if derivation['variant'] == 'residual_fixed':
            logs = (ROOT/directory/'bias_reuse_test.log').read_text()
            extra = ROOT/directory/'residual_fixed_test.log'
            if extra.is_file(): logs += extra.read_text()
            require('STARTUP RESIDUAL FIXED EXACT PASS 1024 random sequences; 748 reused rows; 5912 fallbacks'
                    in logs, 'missing residual fixed-factor integration edge gate')
        if derivation['variant'] in ('rolling_fixed', 'local_rows', 'local_bias'):
            logs = (ROOT/directory/'bias_reuse_test.log').read_text()
            extra = ROOT/directory/'rolling_tag_test.log'
            if extra.is_file(): logs += extra.read_text()
            for marker in (
                    'STARTUP ROLLING REUSE EXACT PASS 1024 sequences; 3648 reused rows; 3168 fallbacks',
                    'STARTUP RESIDUAL FIXED EXACT PASS 1024 random sequences; 1399 reused rows; 5912 fallbacks',
                    'STARTUP ROLLING TAG EXACT PASS 256 sequences; 576 reused rows; 576 fallbacks'):
                require(marker in logs, 'missing rolling metadata lifetime/exactness gate')
            if derivation['variant'] in ('local_rows', 'local_bias'):
                require('STARTUP LOCAL PROJECT EXACT PASS 48 boundary sequences' in logs,
                        'missing local-score scratch boundary/lifetime gate')
            if derivation['variant'] == 'local_bias':
                require('STARTUP LOCAL BIAS EXACT PASS 30 boundary sequences' in logs,
                        'missing exact narrow-bias fit/rejection and local-clobber gate')
        ready_log = (ROOT/directory/'ready_test.log').read_text()
        require('CONTEXT READY FULL MODEL EXACT PASS 60' in ready_log and
                'CONTEXT READY REJECTION PASS 17' in ready_log, 'full-model/nonmutation gate missing')
    from scripts.m5_startup_fetch import check as check_fetch
    check_fetch(ROOT/s['synthesis']/'resolved_sources')
    check_fetch(ROOT/s['model']/'sim')
    for directory in (ROOT/s['synthesis']/'resolved_sources', ROOT/s['model']/'sim'):
        require((directory/'M5_STARTUP_DIRECT_RETURN').is_file(), 'wrong router variant')
    require(read(Path(s['synthesis'])/'resolved_sources/startup_fetch_sources.json') ==
            read(Path(s['model'])/'sim/startup_fetch_sources.json'), 'simulation and synthesized RTL differ')
    fetch_config = read(Path(s['model'])/'sim/startup_fetch_sources.json')
    require(fetch_config.get('data_read_mirror', False) == data_read_mirror,
            'selected data-read resource contract differs from RTL')
    require(fetch_config.get('direct_data_response', False) == s.get('direct_data_response', False) and
            fetch_config.get('extra_data_bram_bytes', 0) == (65536 if data_read_mirror else 0),
            'selected data response/physical capacity differs from RTL')
    from scripts.m5_startup_fetch import TOP
    require(sha(ROOT/s['router']/'pa_m5_obi_router.sv') ==
            sha(ROOT/s['model']/'sim'/Path(TOP).parent/'pa_m5_obi_router.sv'),
            'scoreboard tested a different router')
    if fetch_config['sequential_prefetch']:
        require(fetch_config['sync_lookahead'], 'asynchronous lookahead is not qualified')
        log = (ROOT/s['router']/'test_3.log').read_text()
        require('PASS direct=1 early=0 instant=1 requests=1000 responses=1000' in log and
                all(int(re.search(name+r'=(\d+)', log)[1]) > 0 for name in
                    ('handovers', 'stopped_owned', 'instant_completions')),
                'same-cycle lookahead ownership/stop coverage missing')
    reset_review = (ROOT/s['reset_review_log']).read_text()
    require(f'M5_STARTUP_RESET_REVIEW_COMPLETE cells={reset_count}' in reset_review and
            'open_checkpoint '+str(ROOT/s['hardware']/'m5_pynq_final.dcp') in reset_review,
            'actual final reset-cone review missing')
    cells = re.findall(r'^RESET_CELL .* INIT=(.*)$', reset_review, re.M)
    require(cells.count("4'h7") == reset_count-1 and cells.count("8'hEF") == 1 and len(cells) == reset_count,
            'reviewed reset truth tables changed')
    starts = set()
    for line in reset_review.splitlines():
        if line.startswith('RESET_INPUT '): starts.update(line.split(' STARTS=')[1].split())
    require(starts == {
        'system_i/rst_fclk0/U0/ACTIVE_LOW_PR_OUT_DFF[0].FDRE_PER_N/C',
        'system_i/control_gpio/U0/gpio_core_1/Not_Dual.gpio_Data_Out_reg[4]/C',
        'system_i/control_gpio/U0/gpio_core_1/Not_Dual.gpio_Data_Out_reg[3]/C',
        'system_i/control_gpio/U0/gpio_core_1/Not_Dual.gpio_Data_Out_reg[0]/C',
        'system_i/pa_cluster_m5_0/inst/impl/g_autonomous.u_accelerators/u_transfer/fault_abort_o_reg/C',
        'system_i/pa_cluster_m5_0/inst/impl/g_autonomous.u_accelerators/u_control/abort_request_o_reg/C',
        'system_i/pa_cluster_m5_0/inst/impl/g_autonomous.u_accelerators/cancel_q_reg/C'},
        'unreviewed asynchronous reset source')
    for key, filename, marker in (
            ('memory', 'test.log', 'M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS boots=2 aborted_boots=1'),
            ('accelerators', 'test.log', 'M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1'),
            ('accelerators', 'delayed.log', 'M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1'),
            ('probe', 'probe.log', 'STARTUP FETCH MIRROR PROBE EXACT / RESET-RELOAD PASS'),
            ('router', 'test_0.log', 'requests=1000 responses=1000'),
            ('router', 'test_1.log', 'requests=1000 responses=1000')):
        require(marker in (ROOT/s[key]/filename).read_text(), 'selected RTL regression missing '+key)
    model_archive = str(Path(s['model'])/'sim/Vpa_m5_cluster_top__ALL.a')
    for key in ('memory', 'accelerators', 'probe'):
        manifest = read(Path(s[key])/'manifest.json')
        require(manifest['inputs'][model_archive] == sha(ROOT/model_archive), 'test linked a different RTL model')
        for filename, digest in manifest['generated'].items():
            require(sha(ROOT/s[key]/filename) == digest, 'generated regression file changed')
    campaigns = {str(p.parent.relative_to(ROOT)) for p in ROOT.glob('build/m5_startup_*/campaign.json')}
    require(set(evidence['reports']) == campaigns, 'a retained physical trial was omitted')
    for directory in campaigns:
        r, refs = validate_stage(directory)
        require(r == evidence['reports'][directory] and refs == evidence['references'][directory], 'embedded evidence changed')
    sources, artifacts = manifest_paths()
    require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts, 'manifest coverage changed')
    for category in ('sources', 'artifacts'):
        for path, digest in evidence[category].items():
            require(sha(ROOT/path) == digest, 'changed '+path)


def collect(selection):
    reports, references = {}, {}
    for path in sorted(ROOT.glob('build/m5_startup_*/campaign.json')):
        name = str(path.parent.relative_to(ROOT))
        reports[name], references[name] = validate_stage(name)
    sources, artifacts = manifest_paths()
    e = dict(schema=1, status='PASS', m6_started=False, selection=selection,
        baseline_evidence_sha256=sha(ROOT/'docs/m5_context_evidence.json'),
        binaries={n: sha(ROOT/selection['firmware']/n) for n in
                  ('m5_runtime.bin', 'm5_profile.bin', 'm5_detail.bin', 'm5_trace.bin')},
        overlay={n: sha(ROOT/selection['hardware']/n) for n in ('m5_pynq.bit', 'm5_pynq.hwh')},
        hardware=hardware_from_reports(selection['hardware'], selection['reviewed_reset_count'],
                                       selection.get('data_read_mirror', False)), reports=reports, references=references,
        summary=summarize(reports), sources={p: sha(ROOT/p) for p in sorted(sources)},
        artifacts={p: sha(ROOT/p) for p in sorted(artifacts)})
    validate(e)
    return e


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--campaign', type=Path)
    p.add_argument('--collect', type=Path, metavar='SELECTION_JSON')
    a = p.parse_args()
    if a.campaign:
        validate_stage(a.campaign)
        print('STARTUP CAMPAIGN INTEGRITY PASS (not a final performance closure)')
    else:
        path = ROOT/'docs/m5_startup_evidence.json'
        if a.collect:
            if path.exists(): raise ValueError('refusing to overwrite frozen startup evidence')
            evidence = collect(read(a.collect))
            path.write_text(json.dumps(evidence, indent=2)+'\n')
        validate(read(path))
        subprocess.run([sys.executable, '-m', 'scripts.audit_m5_context'], cwd=ROOT, check=True)
        subprocess.run([sys.executable, '-m', 'unittest', 'tests.m5_startup.test_measurement',
                        'tests.m5_startup.test_runner', 'tests.m5_startup.test_audit'], cwd=ROOT, check=True)
        print('M5 STARTUP AUDIT PASS: exact repeated short requests, charged cold init, max-context delivery, hardware, safe release')


if __name__ == '__main__': main()

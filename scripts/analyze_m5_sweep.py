"""Separate prompt-inclusive delivery, finite continuation, and injected decode."""
import argparse
import csv
import io
import json
from pathlib import Path
import statistics


def stats(values):
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                min=min(values), max=max(values), population_stddev=statistics.pstdev(values))


def summarize(campaign):
    rows, groups, phases = [], {}, []
    for item in campaign['trials']:
        trial = item['trial']
        row = dict(id=trial['id'], kind=trial['kind'], status=item['status'],
                   role=trial['role'], reason=item.get('reason', item.get('error', '')),
                   case_elapsed_seconds=item.get('case_elapsed_seconds', ''),
                   bound_exceeded=item.get('bound_exceeded', ''))
        if item['status'] != 'PASS':
            rows.append(row)
            continue
        r = item['result']
        if trial['kind'] == 'full':
            n = len(r['generated_tokens'])
            model, delivered = r['firmware_seconds'], r['request_through_delivery_seconds']
            prompt = len(r['prompt_tokens'])
            row.update(prompt_tokens=prompt, new_tokens=n, past='', profiled=False,
                       model_first_token_seconds=r['ttft_seconds'],
                       prefill_seconds=r['prefill_forward_seconds'],
                       prefill_tokens_per_second=prompt/r['prefill_forward_seconds'],
                       continuation_tokens=n-1, continuation_seconds=sum(r['decode_seconds']),
                       continuation_tokens_per_second=(n-1)/sum(r['decode_seconds']) if n > 1 else '',
                       workspace_bytes=r['work_high_water'], input_bytes=r['tensor_bytes_read'],
                       output_bytes=r['tensor_bytes_written'], jobs=r['transfers'],
                       traffic_scope='packet byte counters modulo 2^32; not total DDR traffic')
            key = f'full:{trial["case"]}:g{n}'
        else:
            n = 1
            model, delivered = r['model_seconds'], r['host_request_through_delivery_seconds']
            row.update(prompt_tokens='', new_tokens=1, past=trial['past'], profiled=trial['profile'],
                       workspace_bytes=r['workspace_high_water'], input_bytes=r['mover_input_bytes'],
                       output_bytes=r['mover_output_bytes'], jobs=r['jobs'],
                       traffic_scope='packet word counters modulo 2^32, multiplied by 4; not total DDR traffic')
            key = f'cached:p{trial["past"]}:{"profile" if trial["profile"] else "plain"}'
            if trial['profile']:
                totals = {}
                for p in r['phases']:
                    target = totals.setdefault(p['name'], dict(cycles=0, service_cycles=0,
                        cpu_remainder_cycles=0, gemm_cycles=0, sfpu_cycles=0, jobs=0, input_bytes=0, output_bytes=0))
                    for name in target:
                        target[name] += p[name]
                phases.append(dict(id=trial['id'], past=trial['past'], model_seconds=model,
                    service_seconds=r['service_seconds'], cpu_remainder_seconds=r['cpu_remainder_seconds'],
                    cpu_remainder_fraction=r['cpu_remainder_seconds']/model,
                    gemm_compute_seconds=r['gemm_compute_seconds'],
                    sfpu_compute_seconds=r['sfpu_compute_seconds'], phases=totals))
        row.update(model_seconds=model, model_cycles=round(model*campaign['clock_hz']),
                   delivered_seconds=delivered, host_minus_model_seconds=delivered-model,
                   model_tokens_per_second=n/model, delivered_tokens_per_second=n/delivered,
                   case_elapsed_seconds=item['case_elapsed_seconds'], bound_exceeded=item['bound_exceeded'])
        groups.setdefault(key, []).append(row)
        rows.append(row)
    grouped = {}
    metrics = ('model_seconds', 'delivered_seconds', 'delivered_tokens_per_second',
               'prefill_seconds', 'prefill_tokens_per_second', 'model_first_token_seconds',
               'continuation_seconds', 'continuation_tokens_per_second')
    for name, samples in groups.items():
        grouped[name] = {metric: stats([s[metric] for s in samples]) for metric in metrics
                         if metric in samples[0] and samples[0][metric] != ''}
        grouped[name]['sample_ids'] = [s['id'] for s in samples]
        grouped[name]['aggregate_delivered_tokens_per_second'] = sum(s['new_tokens'] for s in samples)/sum(s['delivered_seconds'] for s in samples)
    full = [r for r in rows if r['status'] == 'PASS' and r['kind'] == 'full']
    return dict(schema=1, rows=rows, groups=grouped, profiles=phases,
        coverage=dict(planned_trials=len(campaign['policy']['matrix']) if 'policy' in campaign else len(rows),
                      full_request_prompt_lengths=sorted({r['prompt_tokens'] for r in full}),
                      full_request_output_lengths=sorted({r['new_tokens'] for r in full}),
                      cached_past=sorted({r['past'] for r in rows if r['status'] == 'PASS' and r['kind'] == 'cached'}),
                      profiled_past=sorted(p['past'] for p in phases),
                      uninterrupted_16_token_requests=sum(r['new_tokens'] == 16 for r in full)),
        max_workspace_bytes=max((r['workspace_bytes'] for r in rows if r['status'] == 'PASS'), default=0),
        full_input_tokens=sum(r['prompt_tokens'] for r in full),
        full_generated_tokens=sum(r['new_tokens'] for r in full),
        full_request_aggregate_tokens_per_second=(sum(r['new_tokens'] for r in full)/sum(r['delivered_seconds'] for r in full)) if full else None,
        fully_charged_campaign_full_tokens_per_second=sum(r['new_tokens'] for r in full)/campaign['elapsed_seconds'],
        fully_charged_scope='Full-request output tokens / entire campaign wall time, charging staging, provisioning, all diagnostics, cache injections, checks and cleanup; NOT application throughput.',
        provision_seconds=campaign['provision_seconds'], campaign_seconds=campaign['elapsed_seconds'],
        pass_count=sum(r['status'] == 'PASS' for r in rows),
        skip_count=sum(r['status'] == 'SKIP' for r in rows),
        fail_count=sum(r['status'] == 'FAIL' for r in rows))


def csv_text(summary):
    fields = list(dict.fromkeys(key for row in summary['rows'] for key in row))
    output = io.StringIO()
    writer = csv.DictWriter(output, fields)
    writer.writeheader()
    writer.writerows(summary['rows'])
    return output.getvalue()


def continuation_csv(campaign):
    output = io.StringIO()
    fields = ('id', 'generated_token_ordinal', 'past_before_forward', 'model_interval_seconds',
              'model_interval_tokens_per_second')
    writer = csv.DictWriter(output, fields)
    writer.writeheader()
    for item in campaign['trials']:
        if item['status'] != 'PASS' or item['trial']['kind'] != 'full':
            continue
        r = item['result']
        for ordinal, seconds in enumerate(r['decode_seconds'], 2):
            writer.writerow(dict(id=item['trial']['id'], generated_token_ordinal=ordinal,
                past_before_forward=len(r['prompt_tokens'])+ordinal-2,
                model_interval_seconds=seconds, model_interval_tokens_per_second=1/seconds))
    return output.getvalue()


def tables(summary):
    text = ['# Recorded sweep tables', '',
        'Generated from every passing observation; raw skips/failures remain in the CSV and campaign.', '',
        '## Full requests: on-board prompt processing included', '',
        '| Prompt | Input tokens | New tokens | Repeats | Mean model, s | Mean delivered, s | Aggregate new tokens/s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key, g in summary['groups'].items():
        if not key.startswith('full:'):
            continue
        r = next(r for r in summary['rows'] if r['id'] == g['sample_ids'][0])
        text.append(f'| {key.split(":")[1]} | {r["prompt_tokens"]} | {r["new_tokens"]} | {len(g["sample_ids"])} | '
                    f'{g["model_seconds"]["mean"]:.3f} | {g["delivered_seconds"]["mean"]:.3f} | {g["aggregate_delivered_tokens_per_second"]:.5f} |')
    text += ['', '## Prefill and internal continuation', '',
        'First-token time is a model timestamp, **not streamed delivered TTFT**. Continuation',
        'excludes prefill and host return; tokens are delivered together after the request.', '',
        '| Request | Mean prefill, s | Prefill input tokens/s | Model first token, s | Mean finite continuation tokens/s |',
        '|---|---:|---:|---:|---:|']
    for key, g in summary['groups'].items():
        if key.startswith('full:'):
            continuation = g.get('continuation_tokens_per_second', {}).get('mean')
            text.append(f'| {key[5:]} | {g["prefill_seconds"]["mean"]:.3f} | {g["prefill_tokens_per_second"]["mean"]:.5f} | '
                        f'{g["model_first_token_seconds"]["mean"]:.3f} | {continuation:.5f} |' if continuation is not None else
                        f'| {key[5:]} | {g["prefill_seconds"]["mean"]:.3f} | {g["prefill_tokens_per_second"]["mean"]:.5f} | '
                        f'{g["model_first_token_seconds"]["mean"]:.3f} | — |')
    text += ['', '## Injected valid-cache decode, profiling disabled', '',
        'Independent native prefill and seed restoration are outside this request boundary.', '',
        '| Past | n | Mean model, s | Mean delivered, s | Delivered min–max, s | Population σ, s | Aggregate tokens/s |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    for key, g in sorted(summary['groups'].items(), key=lambda item: int(item[0].split(':')[1][1:]) if item[0].startswith('cached:') else -1):
        if key.startswith('cached:') and key.endswith(':plain'):
            d = g['delivered_seconds']
            text.append(f'| {key.split(":")[1][1:]} | {d["n"]} | {g["model_seconds"]["mean"]:.3f} | {d["mean"]:.3f} | '
                        f'{d["min"]:.3f}–{d["max"]:.3f} | {d["population_stddev"]:.5f} | {g["aggregate_delivered_tokens_per_second"]:.5f} |')
    text += ['', '## Diagnostic phase totals', '',
        'GEMM and SFPU are **inside** service, not additional time. The remainder includes',
        'CPU work, control and scalar-memory latency; it is not an arithmetic-only counter.', '',
        '| Past | Model, s | Remainder, s (%) | Service, s | GEMM, s | SFPU, s |',
        '|---:|---:|---:|---:|---:|---:|']
    for p in summary['profiles']:
        text.append(f'| {p["past"]} | {p["model_seconds"]:.3f} | {p["cpu_remainder_seconds"]:.3f} ({100*p["cpu_remainder_fraction"]:.2f}%) | '
                    f'{p["service_seconds"]:.3f} | {p["gemm_compute_seconds"]:.3f} | {p["sfpu_compute_seconds"]:.3f} |')
    text += ['', 'All samples, per-token continuation intervals, phase counters, traffic and workspace',
             'are preserved in the embedded machine evidence and ignored build CSV/JSON artifacts.', '']
    return '\n'.join(text)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, default=Path('build/m5_sweep_v1'))
    args = parser.parse_args()
    campaign = json.loads((args.stage/'campaign.json').read_text())
    summary = summarize(campaign)
    (args.stage/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (args.stage/'samples.csv').write_text(csv_text(summary))
    (args.stage/'continuation.csv').write_text(continuation_csv(campaign))
    (args.stage/'tables.md').write_text(tables(summary))
    print(json.dumps({k: v for k, v in summary.items() if k not in ('rows', 'groups', 'profiles')}, indent=2))


if __name__ == '__main__':
    main()

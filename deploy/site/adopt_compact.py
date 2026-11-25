"""Re-store an existing SYNTHETIC Monthly Parquet dataset as plain Compact Tick Parquet, keeping its dataset identity.

  python adopt_compact.py --root <monthly root> --dataset-id ID --dataset-version HEX --manifest-sha256 HEX --out <new folder>

Writes `<out>/<YYYY-MM>/ticks.parquet`, `<out>/compact.json` and the adopted `<out>/manifest.json` (canonical authority copied unchanged, storage entries
re-pointed at the Compact files), then reads EVERY event back through CompactBackedMonthlyProvider and requires it to equal the source event.
Refuses anything that is not SYNTHETIC. Never modifies or deletes the source. Prints the environment lines that pin the new source (no secrets).
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--dataset-version', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    from market_data.compact_monthly_provider import CompactBackedMonthlyProvider, admission_record, write_adopted_manifest
    from market_data.compact_tick import write_compact
    from market_data.monthly_parquet import MonthlyParquetProvider
    source = MonthlyParquetProvider(args.root, expected_dataset_id=args.dataset_id, expected_dataset_version=args.dataset_version,
                                    expected_manifest_hash=args.manifest_sha256)
    described = source.describe(args.dataset_id, args.dataset_version)
    if not (described['evidenceClass'] == 'SYNTHETIC_CONTRACT_ONLY' and described['rights']['class'] == 'SYNTHETIC'):
        raise SystemExit('REFUSED: only SYNTHETIC datasets can be adopted by this tool')
    first, last = int(source.manifest['files'][0]['firstTimeNs']), int(source.manifest['files'][-1]['lastTimeNs'])
    quality = next(source.iter_range(first, first + 1))['quality']['evidenceHash']
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f'REFUSED: {out} already exists (immutable output)')
    print('writing Compact files ...', flush=True)
    compact = write_compact(str(out), source.iter_range(first, last + 1), parent=dict(datasetId=args.dataset_id, datasetVersion=args.dataset_version),
                            scale=2, evidence_class='SYNTHETIC_CONTRACT_ONLY', rights={'class': 'SYNTHETIC', 'evidenceHash': None})
    reference = json.loads((Path(args.root) / 'manifest.json').read_bytes())
    adopted = write_adopted_manifest(out, reference, compact)
    print('verifying every event against the source ...', flush=True)
    target = CompactBackedMonthlyProvider(str(out), admission=admission_record(quality), expected_manifest_hash=adopted['manifestHash'],
                                          expected_compact_manifest_hash=compact['manifestHash'], expected_dataset_id=args.dataset_id,
                                          expected_dataset_version=args.dataset_version)
    if target.describe(args.dataset_id, args.dataset_version) != described:
        raise SystemExit('MISMATCH: canonical source manifest differs')
    count = 0
    for a, b in zip(source.iter_range(first, last + 1), target.iter_range(first, last + 1)):
        if a != b:
            raise SystemExit(f'MISMATCH at event {count}')
        count += 1
    if count != source.manifest['eventCount'] or target.verify_all()['status'] != 'PASS':
        raise SystemExit('MISMATCH: count or verification failed')
    size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    print(f'OK: {count} events identical; {size / 1e6:.2f} MB on disk (source {sum(f["bytes"] for f in source.manifest["files"]) / 1e6:.2f} MB)')
    print('ENV BTL_QA_SYNTHETIC_MONTHLY_ROOT=' + str(out.resolve()))
    print('ENV BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256=' + adopted['manifestHash'])
    print('ENV BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256=' + compact['manifestHash'])
    print('ENV BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256=' + quality)


if __name__ == '__main__':
    main()

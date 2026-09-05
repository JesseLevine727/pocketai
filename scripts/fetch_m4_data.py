#!/usr/bin/env python3
"""Pinned WikiText-2 raw assets; separate splits and selection are explicit."""
import argparse
import json
from pathlib import Path
from scripts.fetch_m4_model import fetch, identity

REVISION = 'b08601e04326c79dfdd32d625aee71d232d685c3'
ASSETS = {
    'train': (6357543, 'e83889baabc497075506f91975be5fac0d45c5290b6b20582c8cd1e853d0c9f7'),
    'validation': (657209, '204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c'),
    'test': (732610, '5f1bea067869d04849c0f975a2b29c4ff47d867f484f5010ea5e861eab246d91'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('build/m4_data'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'repository': 'Salesforce/wikitext', 'revision': REVISION,
                'configuration': 'wikitext-2-raw-v1',
                'license': ['CC-BY-SA-3.0', 'GFDL'], 'files': {}}
    for split, (size, digest) in ASSETS.items():
        name = f'{split}-00000-of-00001.parquet'
        url = f'https://huggingface.co/datasets/Salesforce/wikitext/resolve/{REVISION}/wikitext-2-raw-v1/{name}'
        target = args.output / name
        fetch(url, target, size, 'sha256', digest)
        manifest['files'][name] = {'url': url, 'sha256': identity(target), 'size': size}
    url = f'https://huggingface.co/datasets/Salesforce/wikitext/resolve/{REVISION}/README.md'
    target = args.output / 'README.md'
    fetch(url, target)
    manifest['files']['README.md'] = {'url': url, 'sha256': identity(target)}
    (args.output / 'data_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('M4 DATA FETCH PASS (identity only; no quality evaluation yet)')


if __name__ == '__main__':
    main()

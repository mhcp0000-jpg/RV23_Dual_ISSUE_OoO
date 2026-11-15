from pathlib import Path
import argparse
import hashlib
import json
from sim_runner import source_inputs

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--update', action='store_true')
args = parser.parse_args()
manifest_path = ROOT / 'docs/source_manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
imported = json.loads((ROOT / 'docs/import_manifest.json').read_text(encoding='utf-8-sig'))
original = {item['path']: item['sha256'].lower() for item in imported}
sources = (ROOT / 'rtl/filelist.f').read_text().splitlines()
assert sources == (ROOT / 'sim/sources.f').read_text().splitlines(), 'Source lists differ'
assert len(sources) == len(set(sources)), 'Duplicate source entries'
current = []
headers=[{'path':p,'sha256':h} for p,h in source_inputs(sources).items() if p not in sources]
for relative in sources:
    digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    current.append({'path': relative, 'sha256': digest, 'origin':
        'reused' if original.get(relative) == digest else
        'modified' if relative in original else 'new'})
if args.update:
    manifest['files'] = current
    manifest['headers'] = headers
    manifest['removed_from_build'] = [p for p in original if p not in sources]
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
else:
    assert manifest['files'] == current, 'Source manifest differs from current RTL'
    assert manifest.get('headers') == headers, 'Source manifest differs from included headers'
print('PASS source manifest:', len(current), 'RTL files;',
      ', '.join(f'{kind}={sum(x["origin"] == kind for x in current)}'
                for kind in ['reused', 'modified', 'new']))

"""Seal the current audited feature checkpoint without copying object trees."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from sim_runner import ROOT,sha,dump

parser=argparse.ArgumentParser()
parser.add_argument('name')
args=parser.parse_args()
assert args.name and all(c.isalnum() or c in '_-' for c in args.name)
destination=ROOT/'out/checkpoints'/args.name
assert not destination.exists(),f'Checkpoint already exists: {destination}'
audits=[['check_manifest.py'],['audit_hypervisor_integration.py'],['audit_vector_components.py'],
        ['audit_vector_integration.py'],['audit_timing_contract.py'],['audit_upstream_riscv_tests.py'],
        ['audit_rva23_requirements.py','--with-evidence']]
for audit in audits:subprocess.run([sys.executable,str(ROOT/'scripts'/audit[0]),*audit[1:]],cwd=ROOT,check=True)
destination.mkdir(parents=True)
copied=set()
def copy(relative):
    relative=Path(relative).as_posix()
    if relative in copied:return
    source=ROOT/relative;target=destination/relative
    assert source.resolve().is_relative_to(ROOT.resolve()),relative
    assert target.resolve().is_relative_to(destination.resolve()),relative
    assert source.is_file(),relative
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);copied.add(relative)

for tree in ['rtl','scripts','config','sim','sw/tests','sw/benchmarks/coremark','tb','docs']:
    for path in (ROOT/tree).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:copy(path.relative_to(ROOT))
copy('AGENTS.md')
excluded={'privileged_instruction_matrix_fence','privileged_instruction_matrix_wfi','privileged_instruction_matrix_csr','privileged_instruction_matrix_pmp'}
for path in (ROOT/'out/rva23').rglob('*'):
    if path.is_file() and not excluded.intersection(path.relative_to(ROOT/'out/rva23').parts):copy(path.relative_to(ROOT))

# Reports bind exact source paths, model executables, generated vectors and
# logs. Copy only this dependency closure, never generated C++/object folders.
prefixes=('rtl/','tb/','scripts/','config/','sw/','sim/','out/','third_party/')
queue=[p for p in copied if p.startswith('out/rva23/') and p.endswith('.json')]
seen=set()
def references(node):
    if isinstance(node,str):
        if node.startswith(prefixes):
            try:
                if (ROOT/node).is_file():yield node
            except OSError:pass
    elif isinstance(node,dict):
        for key,value in node.items():yield from references(key);yield from references(value)
    elif isinstance(node,list):
        for value in node:yield from references(value)
while queue:
    relative=queue.pop()
    if relative in seen:continue
    seen.add(relative)
    try:record=json.loads((ROOT/relative).read_text(encoding='utf-8'))
    except (ValueError,UnicodeError):continue
    for reference in references(record):
        copy(reference)
        if reference.endswith('.json') and reference not in seen:queue.append(reference)
for path in ['out/rv32_release_audit.json','docs/verification_snapshot.json']:
    copy(path)
checkpoint=json.loads((ROOT/'out/rva23/functional_checkpoint.json').read_text(encoding='utf-8'))
(destination/'SCOPE.txt').write_text(
    'Source/evidence checkpoint for the RVA23 privileged audit fixes.\n'
    f'The active source passed the {len(checkpoint["steps"])}-step implemented-feature checkpoint, 152 upstream user-level tests, '
    '16 upstream M/S tests, the 390-case native privilege matrix, 33 breakpoint metadata cases, '
    '10 MPRV fault cases and 25 saved-ELF replays on the full H/V SoC.\n'
    'A pinned independent Sail model passed the same 168 functional ELFs; 152 user ISA traces '
    'matched 61,754 retirements exactly, and the corrupted-writeback control was rejected. '
    'This remains finite differential evidence, not full ACT4/profile certification.\n'
    'H/V/timing/upstream/requirement evidence audits are rerun inside this copy. The archive contains '
    'the report dependency closure, binaries and logs, without generated object trees.\n'
    'The six-gate RV32 release passed in the active project; its summary is retained here, but all '
    'historical RV32 controls and simulator binaries are not duplicated.\n'
    'No full architectural certification, exhaustive memory-ordering/timing proof, synthesis/STA '
    'or standard external Debug Module/JTAG completion is claimed. Fixed performance benchmark ELFs are unchanged.\n',
    encoding='utf-8')
for audit in audits:
    subprocess.run([sys.executable,str(destination/'scripts'/audit[0]),*audit[1:]],cwd=destination,check=True)
manifest={p.relative_to(destination).as_posix():sha(p) for p in destination.rglob('*') if p.is_file()}
dump(destination/'CHECKPOINT_SHA256.json',manifest)
for path,digest in manifest.items():assert sha(destination/path)==digest,path
print(f'PASS sealed checkpoint {destination}: {len(manifest)} files',flush=True)

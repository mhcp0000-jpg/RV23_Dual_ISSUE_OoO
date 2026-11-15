# SPDX-License-Identifier: Apache-2.0
"""Require the official ACT self-check to reject a copied ADD-to-SUB mutation."""
import argparse, json, struct, subprocess
from pathlib import Path
from sim_runner import ROOT, sha, dump

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/negative_controls/act4_add_sub')
args=parser.parse_args()
source=ROOT/'out/act4/work/rv23-RVA23S64/elfs/rv64i/I/I-add-00.elf'
folder=ROOT/args.output;folder.mkdir(parents=True,exist_ok=True)
model_path=ROOT/'out/act4/dut/model.json'
model=json.loads(model_path.read_text(encoding='utf-8'))
assert sha(ROOT/model['binary'])==model['binary_sha256']
nm='C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-nm.exe'
symbol='I_add_cg_cp_rs1_b0'
table=subprocess.check_output([nm,str(source)],text=True)
address=int(next(line.split()[0] for line in table.splitlines() if line.endswith(' '+symbol)),16)
image=bytearray(source.read_bytes());assert image[:6]==b'\x7fELF\x02\x01'
phoff=struct.unpack_from('<Q',image,32)[0]
phsize,phcount=struct.unpack_from('<HH',image,54)
offset=None
for index in range(phcount):
    kind,flags,position,virtual,physical,filesize,memsize,align=struct.unpack_from('<IIQQQQQQ',image,phoff+index*phsize)
    if kind==1 and virtual<=address<virtual+filesize:offset=position+address-virtual
assert offset is not None
instruction=struct.unpack_from('<I',image,offset)[0]
assert instruction & 0xfe00707f == 0x33,hex(instruction)
mutated=instruction|0x40000000
struct.pack_into('<I',image,offset,mutated)
target=folder/'I-add-00-mutated.elf';target.write_bytes(image)
command=[str(ROOT/model['binary']),'+elf='+str(target),'+quiet_commit','+timeout_cycles=20000000','+elf_verify=0']
log=folder/'rtl.log'
with log.open('w',encoding='utf-8') as stream:
    result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
output=log.read_text(encoding='utf-8',errors='replace')
passed=result.returncode!=0 and 'RVCP-SUMMARY: TEST FAILED' in output and 'ELF reported failure exit code 1' in output
report=dict(passed=passed,scope='Expected rejection of an intentionally corrupted copy; official test ELF is unchanged',
    original=source.relative_to(ROOT).as_posix(),original_sha256=sha(source),mutant=target.relative_to(ROOT).as_posix(),
    mutant_sha256=sha(target),symbol=symbol,address=hex(address),original_instruction=hex(instruction),
    mutated_instruction=hex(mutated),binary_sha256=model['binary_sha256'],exit_code=result.returncode,
    log_sha256=sha(log),log=log.relative_to(ROOT).as_posix(),command=command)
dump(folder/'report.json',report)
print(output[-2500:],flush=True)
assert passed,'ACT4 self-check did not reject the known wrong instruction'
print('PASS ACT4 negative control: mutated ADD rejected by official self-check and hardware exit',flush=True)

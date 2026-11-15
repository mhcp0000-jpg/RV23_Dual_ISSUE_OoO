"""Install a separate LP64 toolchain for the unmodified official Sail runtime."""
import hashlib
import subprocess
import urllib.request
from pathlib import Path
from sim_runner import ROOT, dump, sha

folder = ROOT / 'out/reference/cygwin'
folder.mkdir(parents=True, exist_ok=True)
installer = Path('C:/rv_toolchains/downloads/setup-x86_64.exe')
base = 'https://cygwin.com/'
checksums = urllib.request.urlopen(base + 'sha512.sum', timeout=30).read()
expected = next(line.split()[0].decode() for line in checksums.splitlines()
                if line.split()[-1] == b'setup-x86_64.exe')
if not installer.exists() or hashlib.sha512(installer.read_bytes()).hexdigest() != expected:
    installer.write_bytes(urllib.request.urlopen(base + installer.name, timeout=60).read())
assert hashlib.sha512(installer.read_bytes()).hexdigest() == expected
(folder / 'setup.sha512').write_bytes(checksums)
command = [str(installer), '--no-admin', '--no-write-registry', '--quiet-mode=hidden',
           '--no-shortcuts', '--no-replaceonreboot', '--only-site',
           '--root', 'C:/rv_toolchains/cygwin-rv23',
           '--local-package-dir', 'C:/rv_toolchains/downloads/cygwin-rv23',
           '--site', 'https://mirrors.kernel.org/sourceware/cygwin/',
           '--packages', 'gcc-g++,cmake,ninja,libgmp-devel,ruby,ruby-devel,make']
report = dict(passed=False, installer_sha512=expected, script_sha256=sha(__file__), command=command)
dump(folder / 'setup_report.json', report)
with (folder / 'setup.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
report['exit_code'] = result.returncode
report['passed'] = result.returncode == 0
dump(folder / 'setup_report.json', report)
assert report['passed'], (folder / 'setup.log').read_text(encoding='utf-8', errors='replace')[-4000:]
print('PASS separate Cygwin LP64 toolchain installation', flush=True)

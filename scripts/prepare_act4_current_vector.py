"""Stage generated vector sources and the RVA23 DUT for current upstream ACT4."""

import json
import shutil

from run_act4_current_h import REVISION, SOURCE, git
from run_act4_upstream_h import NAME as BASE_NAME, dut_configs
from sim_runner import ROOT, dump, sha


FOLDER = 'out/act4/current_vector'
NAME = 'rv23-RVA23S64-current-vector'
SUITES = (
    'Vx8', 'Vx16', 'Vx32', 'Vx64', 'Vls8', 'Vls16', 'Vls32', 'Vls64',
    'Vf32', 'Vf64', 'Zvfhmin', 'Zvbb8', 'Zvbb16', 'Zvbb32', 'Zvbb64',
)
GENERATION_LOG = 'out/act4/current_vector_generation.log'


def main():
    assert git('rev-parse', 'HEAD') == REVISION
    git('diff', '--exit-code', 'HEAD', '--', 'framework', 'generators', 'testplans', 'tests')
    log = (ROOT / GENERATION_LOG).read_text(encoding='utf-8')
    assert 'Generated 30 test suite(s)' in log and 'Traceback' not in log
    folder = ROOT / FOLDER
    sources = {path.relative_to(folder).as_posix(): sha(path)
               for path in (folder / 'tests/rv64i').rglob('*.S')}
    assert {path.split('/')[2] for path in sources} == set(SUITES)
    generator_files = git('ls-tree', '-r', '--name-only', 'HEAD', 'generators/testgen', 'testplans').splitlines()
    generator_hashes = {path: sha(ROOT / SOURCE / path) for path in generator_files}
    config = folder / 'config'
    config.mkdir(exist_ok=True)
    for filename, contents in dut_configs().items():
        (config / filename).write_text(contents.replace(BASE_NAME, NAME), encoding='utf-8')
    env_files = git('ls-tree', '-r', '--name-only', 'HEAD', 'tests/env').splitlines()
    for filename in env_files:
        destination = folder / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / SOURCE / filename, destination)
    counts = {suite: sum(path.startswith('tests/rv64i/' + suite + '/') for path in sources) for suite in SUITES}
    dump(folder / 'source_manifest.json', dict(
        prepared=True, act_commit=REVISION, suites=counts, source_count=len(sources),
        source_sha256=sources, generator_sha256=generator_hashes,
        generation_log_sha256=sha(ROOT / GENERATION_LOG),
        config_sha256={name: sha(config / name) for name in dut_configs()},
        env_sha256={path: sha(folder / path) for path in env_files},
        prepare_script_sha256=sha(__file__)))
    print('Prepared current upstream vector test sources', json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()

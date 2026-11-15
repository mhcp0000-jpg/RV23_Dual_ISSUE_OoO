"""Validate the LP64/GMP assumptions before accepting the native Sail oracle."""
from pathlib import Path
import os
from sim_runner import ROOT, Simulator, sha, dump

folder = ROOT / 'out/reference/host_abi'
folder.mkdir(parents=True, exist_ok=True)
source = folder / 'check.c'
source.write_text(r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <gmp.h>
_Static_assert(sizeof(long) == 8, "Sail runtime requires LP64 long");
_Static_assert(sizeof(mp_limb_t) * 8 == GMP_LIMB_BITS, "GMP limb ABI mismatch");
int main(void) {
    mpz_t n, m; mpz_init(n); mpz_init(m);
    const uint64_t values[] = {0, 1, UINT64_C(0xffffffff), UINT64_C(0x100000000),
        UINT64_C(0x8000000000000000), UINT64_MAX, UINT64_C(0x0123456789abcdef)};
    for (unsigned i=0; i<sizeof(values)/sizeof(values[0]); ++i) {
        mpz_set_ui(n, values[i]); assert(mpz_get_ui(n) == values[i]);
    }
    const int64_t signs[] = {INT64_MIN, INT64_MAX, -INT64_C(0x100000000), -1, 0, 1};
    for (unsigned i=0; i<sizeof(signs)/sizeof(signs[0]); ++i) {
        mpz_set_si(n, signs[i]); assert(mpz_get_si(n) == signs[i]);
    }
    mpz_set_ui(n, 1); mpz_mul_2exp(n, n, 100);
    mpz_sub_ui(m, n, 1); mpz_add_ui(m, m, 1); assert(mpz_cmp(m, n) == 0);
    for (unsigned i=0; i<64; ++i) {
        uint64_t value=UINT64_C(1)<<i;
        mpz_set_ui(n, value); assert(mpz_get_ui(n) == value);
        assert(mpz_scan1(n, 0) == i);
    }
    mpz_clear(n); mpz_clear(m);
    puts("PASS Sail LP64/GMP ABI: 64-bit limbs, full unsigned/signed bounds, 100-bit arithmetic");
}
''', encoding='utf-8')
cygwin = Path('C:/rv_toolchains/cygwin-rv23/bin')
with Simulator() as sim:
    sim.env['PATH'] = str(cygwin) + ';' + os.environ['PATH']
    prefix = '/cygdrive/' + sim.drive[0].lower() + '/out/reference/host_abi/'
    binary = folder / 'check.exe'
    compile_record, _ = sim.run([cygwin / 'gcc.exe', '-std=c11', '-Wall', '-Wextra', '-Werror',
        prefix+'check.c', '-lgmp', '-o', prefix+'check.exe'], folder / 'compile.log', 30)
    run, output = sim.run([binary], folder / 'run.log', 30)
    assert 'PASS Sail LP64/GMP ABI' in output
    dump(folder / 'report.json', dict(passed=True, generator_sha256=sha(__file__),
        source_sha256=sha(source), binary_sha256=sha(binary), compile=compile_record, run=run,
        scope='Host numeric ABI check; no RTL/ISA verdict'))
print(output.strip(), flush=True)

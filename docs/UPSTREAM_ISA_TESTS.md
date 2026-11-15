# Independent upstream instruction regression

`scripts/run_upstream_riscv_tests.py` executes the unmodified instruction tests
from [riscv-tests](https://github.com/riscv-software-src/riscv-tests), pinned to
`3df703cd52d5f0d8224e3c50bf03c6cb70efff98`, with the upstream physical test
environment pinned to `6de71edb142be36319e380ce782c3d1830c65d68`.
Both repositories and their licenses are retained in `third_party/riscv-tests`.

Only the physical environment's final tohost transport is adapted: its test
number is written to the SoC host event register, and test number 1 produces a
zero host exit code. Other values produce failure. The include path is adjusted
for the generated header location. Instruction bodies, expected values, test
macros, boot/privilege setup and exception handlers are unchanged.

The default suite selects all 152 upstream Makefrag tests for RV64 I, M, A, F,
D, C, Zba, Zbb, Zbs and Zicond. `--case suite/name` runs an individual test.
`--resume` accepts a prior case only when its complete input map, executable,
ELF, trace and compile/run logs still match. The final audit additionally checks
the current compiled SoC source/header set and every artifact hash.

`scripts/run_upstream_privileged_tests.py` runs 16 reviewed M/S tests for CSRs,
traps, halfword-aligned fetch, counters, WFI, PMP granularity, Sv39 aliases and
software A/D handling. Optional trigger tests and tests requiring misalignment
traps are outside this selected set: this core implements misalignment assists.
The upstream dirty-bit test explicitly supports software A/D repair (Svade).

All tests run as functional ELFs on the same integrated H-enabled RV64 SoC.
They do not replace or rebuild the preserved performance benchmark ELFs.
Reports are under `out/rva23/upstream_riscv_tests`; independent audit evidence
is `out/rva23/upstream_isa_evidence.json`.

The HostIF-adapted suite above remains separate from the new independent
Sail comparison. `run_sail_upstream_comparison.py` uses the original upstream
physical header without transport adaptation and a shared linker placement
for HTIF. Each resulting functional ELF is identical for Sail and the H/V RTL;
168 programs passed both. Exact comparison of all 152 user-test retirement
prefixes passed 61,754 instructions, including scalar 64-bit writebacks.
The 16 reviewed M/S programs have matching self-checking PASS outcomes;
their entire timing-sensitive retirement streams are not claimed equivalent.

See [SAIL_REFERENCE](SAIL_REFERENCE.md) for pinned tool/model provenance and
host ABI validation. Full [ACT4](https://github.com/riscv/riscv-arch-test)
certification and broader privileged/vector differential coverage remain open.

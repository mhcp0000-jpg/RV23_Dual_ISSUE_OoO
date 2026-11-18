# Official architecture-test verification

Target: complete RVA23S64 on the existing RV64 H/V SoC, with I/D 32 KiB,
64-bit AXI and 1 MiB SRAM. This activity does not change benchmark ELFs.

The official `riscv-arch-test` release 4.1.0 is pinned at
`6e8a45123f14cebfb3df151a0e7b849b4389b33b`. Its checked-in test sources and
expected-signature transformation are unmodified. The official selector
chooses 663 files from 1,976 candidates using the full-profile DUT UDB config.
All 663 self-checking ELFs built within the 1 MiB RAM map and passed before
the MMIO, Sstc and vector segment PMA changes. The historical result audit is
`out/act4/verification_report.json`. The incomplete generated-vector runs are
preserved under `out/act4/pre_mmio_recovery`. The full ACT4 run follows RTL
implementation and directed checks.

The current RTL passed 663 checked-in and 2,083 generated vector ELFs. The
copied ADD-to-SUB negative control also failed at the intended testcase on
the same binary. `python -X utf8 scripts/audit_act4_results.py --current`
recomputes the result from the current model, test ELFs and logs and writes
`out/act4/current_execution_audit.json`.

The first execution found two LR/SC signature mismatches. The DUT requires
the SC address and width to match its preceding LR. Zalrsc permits failure
for unconstrained sequences with a different address or width. The initial
Sail and UDB configuration had selected the more permissive address policy.
The corrected configuration passed all four LR/SC tests. Both affected
SC ELFs retain byte-identical executable sections and have regenerated
signature data. The original failing artifacts are in
`out/negative_controls/act4_lrsc_policy`.
[Ratified Zalrsc specification](https://raw.githubusercontent.com/riscv/riscv-isa-manual/20240411/src/a-st-ext.adoc)

## Fetch-fault defect found and corrected

The pre-fix RTL completed 207 tests: 206 passed, while
`PMPZca_misaligned_napot-00` failed a branch checkpoint sequence assertion.
The same ELF reproduced the failure with complete AXI segment readback.
`rv_decode2` preserved the original execution/resource classifications when
fetch reported an exception. A faulted JALR could enter the IQ even though
no branch checkpoint was allocated for that exception.

Fetch faults now use the same inert decode path as illegal instructions:
no execution port, destination write, load/store allocation or branch/CSR/fence
classification, while preserving the original fetch cause and fault address
for the precise ROB trap. The new RV32/RV64 two-lane unit test checks 384 faulted
lanes and rejects the saved pre-fix decoder. All 14 official PMPZca ELFs pass
on the corrected H/V SoC with full AXI readback, including the originally
failing ELF. The 70-step feature checkpoint and six-gate RV32 audit both pass.
The unchanged original ELF hashes and pre-fix executable/source snapshot are
under `out/negative_controls/act4_pmp_branch`.

## Reference-model limitation

ACT4 requires Sail 0.13.1. The exact official tag
`27224ccb2290f022e46213c05b3e72e8a9ea635e` was downloaded and built successfully.
Its `model/core/extensions.sail` fixes `hartSupports(Ext_H) = false`; it rejects
the DUT's H exception-delegation mask. The original rejection log is retained
in `out/act4/framework-sail013-H-rejected.log`. Disabling H in the DUT config
would misrepresent the requested core.

This run therefore explicitly uses unmodified official Sail 0.16 commit
`e5acebb04ff573e93203596486b831a5974117c3`, which supports H. The local launcher
changes the required-version constant to 0.16 and prints that exception;
the executable reports its genuine version. No ISA instruction model,
expected result, or generated test was changed. This is compatibility
validation with official ACT4 test content, **not official ACT4 certification**.
Both reference builds use Cygwin x86-64 LP64. The local host driver handles
ELF loading, bounded execution, HTIF exit and signature-file output.

## DUT configuration and Windows support

`config/act4/rv23` contains the full profile configuration, linker script,
Sail configuration and real SoC console/exit/interrupt hooks. `.text.rvmodel`
follows `.data`, preserving reference/DUT data addresses. Tests use the actual
CLINT and PLIC hooks. Reference-only interrupt-generator IO occupies a separate
address. The ACT harness expands only its ELF loader window to the existing
1 MiB SRAM; production RTL is unchanged.

UDB 0.1.16's guest-interrupt-count schema incorrectly requires at least one
guest external interrupt. The local overlay changes only its minimum to zero,
matching DUT GEILEN=0 and the H 1.0 specification. Configuration validation
then succeeds. All mandatory extensions remain selected.

The process-local Ruby support resolves actual `.exe` tool paths and disables
the IDL compiler's progress-bar helper, whose `fork()` is unavailable in native
Windows Ruby. Parsing, type checking, configuration constraints and Z3 remain
active. Official test and reference repositories remain unmodified.
The local ACT launcher also streams each assembly configuration prefix through
ACT's unchanged strict YAML parser. This avoids loading the large vector test
body while selecting tests. Equality against the official full-file parser was
checked on 12 scalar/vector source files; the compiler still consumes each
complete source file. Generated vector sources live in the separate worktree.

## Evidence and coverage boundary

- `out/act4/inventory.json`: all candidates, selection/exclusion reasons,
  selected suites, source/ELF hashes and test-requirement gaps.
- `out/act4/dut/results.json`: actual RTL exit status, exact ACT summary,
  per-test logs, ELF hashes and model hash. Incremental while tests run.
- `out/act4/dut/model.json`: full H/V RTL/TB inputs and binary provenance.
- `out/act4/sail-0.13.1/library_report.json`: exact required reference build.
- `out/act4/sail-0.16/driver_report.json`: H-capable reference driver/version.
- `out/act4/framework.log`: official framework ELF-generation result.

A pass requires both the official `RVCP-SUMMARY: TEST PASSED` witness and the
RTL harness's successful hardware exit. A successful process without that
ACT witness is not counted as a pass. Timeouts and failures remain failures.
The initial runs include full AXI readback of every ELF segment. Subsequent
runs may use the existing `+elf_verify=0` option to omit that repeated loader
readback; actual loading still uses AXI writes. Each saved command records the
option. The official ELF and architectural self-check are identical. A copied
ADD-to-SUB mutation was rejected at its first testcase, with the expected/bad
values and hardware failure exit. Its evidence is under
`out/negative_controls/act4_add_sub`; the original ELF is unmodified.

The initial checked-in selection does **not** provide explicit V or H tests.
The main Vx/Vls and standalone Vf generators produced 2,083 test sources in
the detached pinned worktree `out/act4/vector-source`. The original 1 MiB
test layout linked 2,063 ELFs. The 20 FP comparison tests that exceeded the
layout linked with a 32 KiB test stack within the same 1 MiB RAM. The linker
inputs and source hashes for that build are in `out/act4/vector-small-stack`.
RTL execution reports are `out/act4/dut/vector.json` and
`out/act4/dut/vector-small-stack.json`. Build counts and RTL pass counts are
tracked separately. The initial suites also leave
profile contracts such as data-independent timing and several privileged
extensions without direct suite coverage. Aggregate A/B/C extension names
may be absent from requirements because their constituent extensions have
tests; the inventory's requirement-gap list is not itself a missing-hardware
list. These ACT results must be combined with the separate V/H and timing
evidence, and still cannot establish complete profile certification.

Reproduce ELF generation with `python -X utf8 scripts/run_act4.py --fast --keep-going`.
Execute the resulting ELFs with `python -X utf8 scripts/run_act4_dut.py`.

For a rerun on a rebuilt RTL harness, use --inventory-selected for the
663 checked-in ELFs and --vector-only for the 2,083 generated ELFs. The
current-results audit compares the checked-in ELF hashes with the inventory.
For generated vectors, it hashes the canonical mapping of relative ELF names
to SHA-256 digests. The expected digest in `config/act4/rv23/vector_elf_set.json`
was derived from all 2,083 passing vector ELFs in the Svpbmt-fix audit and
checked against the preserved ELF bytes before the HS `sie` rerun.
The execution audit reports passing checked-in tests by literal requirement
tag, and passing generated ELFs by suite. The tags identify what the tests
request from the DUT, and the counts do not establish clause coverage.
Zvbb uses the separate native check in `scripts/run_zvbb_native.py`.

The supplemental H run uses upstream ACT4 commit
`1c3e9f2a89e103eeed0a3e6ba1bc699f100fd481`, whose required Sail version is
0.16. On the RV64 H/V RTL, all 40 selected ELFs passed. Their coverage includes
G-stage translation and permissions, HS/VS invalidation, guest delegation,
NAPOT/PBMT, MPRV with hgatp, cache-block operations and PMP lock readback.
The selector excludes two scalar page-straddle fixtures that require sequential
byte accesses. This DUT declares its custom prevalidated split strategy.
The separate `python scripts/run_guest_misaligned.py` check exercises this
strategy with native VS and VU word accesses and with MPRV+MPV selecting
each guest privilege from M-mode. It checks both halves of a
successful store to nonadjacent SRAM pages, signed and unsigned loads, and
zero memory or destination-register updates when the second page fails
VS-stage or G-stage translation. The 16 translation faults include exact
second-page addresses and guest fault metadata. The M-mode cases also check
the saved actual privilege and virtualization state. Eight more access
faults exercise denying the second page's G-stage or VS-stage PTE read with
PMP. The handler checks the original load/store cause, zero `mtval2` and
`mtinst` after seeding both registers, and unchanged memory.
[Privileged Architecture](https://docs.riscv.org/reference/isa/priv/supervisor.html)
The Windows build uses a copied
DUT config with the implemented HPM3 width and event selector declared for
the test headers. The upstream test instructions are unchanged.
Run `python scripts/run_act4_upstream_h.py` to build and execute the
supplemental set. It retains the upstream source and ELFs under
`out/act4/upstream_h_extended` and records the generating revision in
`out/act4/dut/upstream-h-extended.json`. Recheck the saved artifacts with
`python scripts/run_act4_upstream_h.py --check`.
The original 2,746-ELF regression retains its pinned test inputs.
[Supplemental ACT4 revision](https://github.com/riscv/riscv-arch-test/tree/1c3e9f2a89e103eeed0a3e6ba1bc699f100fd481)

## Newer upstream ACT4 Sail pin

The separate upstream `act4` commit
`8adba12816e0e99c46ccf01626752dbf2e1e40fb` requires Sail 0.16 directly.
The Windows runner used the matching Sail 0.16 model without a version
override. The upstream framework produced four self-checking ELFs. The
current RTL passed all four, covering `hgatp` modes, G-stage PTE rules,
VS guest faults and `hstatus.VTVM`. This run used the existing Windows
toolchain setup and board configuration, including the declared HPM3
parameters. The broader ACT results above retain their original inputs.
[Upstream framework version requirement](https://github.com/riscv/riscv-arch-test/blob/8adba12816e0e99c46ccf01626752dbf2e1e40fb/framework/src/act/config.py#L128)

Build and run with `python scripts/run_act4_current_h.py`. Recheck the
framework inputs, Sail signatures, ELF and RTL execution with
`python scripts/run_act4_current_h.py --check`.
The output is `out/act4/current_h_probe/audit.json`.

Run the broader H, Sv39x4 and PMP selection against this same upstream
revision with `python scripts/run_act4_current_h.py --extended`. The
framework selects 40 out of 42 staged sources, and all 40 generated ELFs
passed on the current RTL. The two page-straddle sources
declare `sequential_bytes` and are filtered by the DUT's split strategy.
Recheck the run with `python scripts/run_act4_current_h.py --extended --check`.
The verification artifacts use `out/act4/current_h_extended/`.

## Checked-in RVA23 certification selection

The upstream `--certificate RVA23` filter selects 607 checked-in cases
from 34 suites with the current DUT configuration, including 516 under
`rv64i` and 91 under `priv`. The planned ELF names
match the framework's suite counts and all 607 generated ELFs. The local
`generation_audit.json` records their hashes and the build log hash. The
RTL execution report is `out/act4/dut/current-rva23-checked-in.json`.
All 607 ELFs passed on the current RTL. Recheck the selection, generated
ELF hashes, Sail signatures, configuration and actual RTL run logs with
`python scripts/audit_act4_current_rva23.py`.
This count covers the checked-in
sources. Generator output from the upstream vector generation step can
extend the inventory. The selection and build directories are
`out/act4/current_rva23_inventory/`. This selection is separate from the
unfiltered H/PMP selection above.
[Upstream RVA23 test workflow](https://github.com/riscv/riscv-arch-test/blob/8adba12816e0e99c46ccf01626752dbf2e1e40fb/docs/RVA23Cert.md)

To reproduce the checked-in run, copy the H probe configuration directory
to `out/act4/current_rva23_inventory/config/` and set the DUT name to
`rv23-RVA23S64-current-inventory` in both YAML files. With the standard
Windows ACT4 toolchain and workspace junction, run the following.

```powershell
$env:RV23_ACT4_PYTHON = '3.13'
$env:RV23_ACT4_SOURCE_ROOT = 'C:/rv_workspaces/rv23/out/act4/upstream_act4_current'
$env:RV23_ACT4_CONFIG = 'C:/rv_workspaces/rv23/out/act4/current_rva23_inventory/config/test_config.yaml'
$env:RV23_ACT4_WORKDIR = 'C:/rv_workspaces/rv23/out/act4/current_rva23_inventory/work'
$env:RV23_ACT4_LOG = 'current_rva23_inventory/build.log'
python scripts/run_act4.py --certificate RVA23 --jobs 6 --keep-going
python scripts/run_act4_dut.py --act-source-root out/act4/upstream_act4_current --elf-root out/act4/current_rva23_inventory/work/rv23-RVA23S64-current-inventory/elfs --report current-rva23-checked-in.json --workers 6 --timeout 1200
```

## Generated vectors on the newer upstream revision

The unmodified generator at `8adba12816e0e99c46ccf01626752dbf2e1e40fb`
produced 2,301 RV64 assembly sources across Vx8/16/32/64, Vls8/16/32/64,
Vf32/64, Zvfhmin and Zvbb8/16/32/64. Source generation completed for all
30 requested XLEN/suite combinations. The generated RV32 counterparts
also remain under the local output directory. The source hashes, generator
inputs and DUT configuration are recorded in
`out/act4/current_vector/source_manifest.json`.

Generate sources from the `out/act4/upstream_act4_current/` directory.

```powershell
uv run --no-dev --python 3.13 testgen testplans -o C:/rv_workspaces/rv23/out/act4/current_vector/tests --extensions Vx8,Vx16,Vx32,Vx64,Vls8,Vls16,Vls32,Vls64,Vf32,Vf64,Zvfhmin,Zvbb8,Zvbb16,Zvbb32,Zvbb64 --jobs 4 *> C:/rv_workspaces/rv23/out/act4/current_vector_generation.log
```

From the workspace root, run `python scripts/prepare_act4_current_vector.py`
after successful generation. Use `RV23_ACT4_CONFIG` at
`C:/rv_workspaces/rv23/out/act4/current_vector/config/test_config.yaml`,
`RV23_ACT4_WORKDIR` at
`C:/rv_workspaces/rv23/out/act4/current_vector/work`, and
`RV23_ACT4_LOG=current_vector/framework.log`. Keep the newer upstream
source root from the checked-in command above, and then run
`python scripts/run_act4.py --certificate RVA23 --test-dir C:/rv_workspaces/rv23/out/act4/current_vector/tests --jobs 6 --keep-going`.
The RVA23 filter selected all 2,301 RV64 sources from the 15 suites above.
The selected counts match the source manifest. Sail generated signatures
for all 2,301 cases, and all 9,204 build tasks completed successfully.
The generation audit checked every signature, reference run log and final
ELF. All 2,301 selected ELFs passed on the current RTL. The full execution
audit passed, including current model and artifact hashes and exact test-file witnesses.
The execution report target is `out/act4/dut/current-rva23-vector.json`.
Run `python scripts/audit_act4_current_vector.py --selection-only` to
recheck source hashes, generator inputs, configuration and the official
selection while the build is in progress.
Use `python scripts/audit_act4_current_vector.py --generation-only` to
recheck the completed signature and ELF generation. Its output is
`out/act4/current_vector/generation_audit.json`.

After ELF generation completes, execute the selected binaries.

```powershell
python scripts/run_act4_dut.py --act-source-root out/act4/upstream_act4_current --elf-root out/act4/current_vector/work/rv23-RVA23S64-current-vector/elfs --report current-rva23-vector.json --workers 12 --timeout 1200
python scripts/audit_act4_current_vector.py
```

The full audit requires all selected RTL runs to pass and verifies the
ELF, Sail signature, execution log and current RTL model hashes.
The completed audit is `out/act4/current_vector/execution_audit.json` and is
required by the integrated RVA23 evidence gate. This is finite architectural
test evidence; `full_profile_verified` remains false.

Run the inventory audit through the ACT uv environment:
`uv run --project third_party/riscv-arch-test --no-dev python -X utf8 scripts/audit_act4_inventory.py`.

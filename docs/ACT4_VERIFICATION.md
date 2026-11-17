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

Run the inventory audit through the ACT uv environment:
`uv run --project third_party/riscv-arch-test --no-dev python -X utf8 scripts/audit_act4_inventory.py`.

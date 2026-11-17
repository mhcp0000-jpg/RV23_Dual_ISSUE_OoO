# H / Sha implementation

H is integrated into the running RV64 SoC. The RV64 top enables HAS_H by
default; explicit RV32 configurations retain HAS_H=0. This is implementation
and directed-test evidence, not full RVA23 architectural sign-off.
The main source lists contain 100 compilation units plus included headers.

The 2026-11-02 CSR/permission audit added VU Svinval ordering-fence cause 22,
bounded U WFI traps, writable M/S/H FIOM, read-only-zero mconfigptr and external
SEIP read/RMW isolation. Non-delegated S interrupts now preserve causes 9/1/5
when targeting M. The CSR component covers 320 intercept contexts, 960
SRET/SFENCE/WFI checks and all 127 nonempty physical M-target IRQ combinations.
A native 250-case matrix verifies 389 precise traps, real decode/retirement and
M/HS/VS/U/VU returns. Sixteen unmodified pinned upstream M/S tests passed on
the same H-enabled SoC; full architectural validation remains separate.

- HLV/HSV/HLVX, HFENCE and HINVAL share the normal decoder and precise ROB-head
  completion path. Encoding/permission checks cover 17 forms, 612 GNU vectors
  and 977,520 encoding/context cases. Actual VS/VU H accesses trap with cause 22;
  HU and TVM restrictions retain machine-denied illegal-instruction priority.
- `rv_csr_file` commits H/VS banks and stateen changes, virtual CSR aliases,
  MPV/GVA, virtual interrupt aliases, htimedelta/vstimecmp and trap metadata.
  Guest FS/VS state is checked against both HS and VS status. The integrated
  CSR test covers M/HS/VS/VU, delegation, interrupts and returns.
- Guest scalar integer/FP, A, CBO and V memory use VS/G contexts. Ordinary guest
  scalar memory initially serializes at ROB head. Aligned element accesses are
  one full-size request, including complete-size PMP checking. Unaligned SRAM
  accesses validate every byte before effects. Device attributes follow the
  physical request; naturally aligned MMIO retains its original size/strobes.
- Sv39x4 translates VS PTE reads as well as final GPAs. HLVX checks X at both
  stages, uses load/SUM privilege and load fault causes, and is exempt from
  pointer masking. HS MXR applies to both stages; VS MXR applies to VS only.
  Ssnpm includes henvcfg.PMM and actual U-mode HLV/HSV hstatus.HUPMM (PMLEN 0/7).
- Guest fetch GPA and implicit-PTE metadata pass through the parcel queue,
  frontend queues and ROB. Explicit final-GPA faults follow the failing parcel;
  implicit VS-PTE addresses retain the PTE address. Serialized guest data faults
  retain metadata under the owning ROB sequence until the accepted trap.
- GEILEN=0 and VMIDLEN=0. VSXL/UXL are fixed to 64. HFENCE/HINVAL conservatively
  invalidate all translations. Unsupported custom/JVT/Zfinx/AIA state is RAZ.
- Unsupported `hgatp.MODE` writes retain MODE and write the aligned root PPN.
  VMID and reserved bits read zero.

## Native execution tests

The following scripts use the same content-bound H-enabled OoO SoC model.
Each report records RTL/TB/model/ELF/trace hashes. Later edits make older reports
historical until the affected runs are repeated. These are functional ELFs;
fixed performance benchmark ELFs are unchanged.

| Script | Directed scope |
|---|---|
| `run_hypervisor_integration.py` | M/HS/VS, VS Sv39, G Bare; HLV/HSV/HLVX; guest scalar/FP/A/CBO/V memory; retained vector state; virtual instruction traps |
| `run_hypervisor_gstage_integration.py` | VS Sv39 plus G Sv39x4 with distinct table/data GPAs; explicit guest store fault; implicit VS-PTE fetch fault; htval/htinst and retry |
| `run_hypervisor_interrupt_integration.py` | VS vectored software and offset-time Sstc interrupts; code renumbering; VS SRET; VU counter/CSR qualification |
| `run_hypervisor_access_integration.py` | MPRV+MPV; actual U-mode HLV/HSV/HU; HUPMM and HLVX pointer-mask exemption |
| `run_hypervisor_vector_faults.py` | Guest partial store/load G-stage faults, retained memory/destination elements, same-PC vstart=2 restart, AMO/CBO guest fault metadata |
| `run_hpm_integration.py` | HS-only and VS-only filtered HPM events, scountovf, overflow IRQs in HS and during guest execution |

## Integration bugs found by the native tests

1. A trap redirect could accept its target fetch before the privilege/V state
   changed. HS handler fetches then inherited guest translation and faulted
   again. The MMU-facing fetch adapter now holds acceptance across the backend
   redirect and translation-control change edge.
2. An immediate interrupt after xRET saved the handler's sequential PC instead
   of the return target. The trap controller now records the return target as
   the architectural instruction boundary. A directed MRET/SRET boundary test
   and native VS interrupt test cover this case.
3. CLINT rejected RV64 timer doubleword accesses. mtime/mtimecmp now support
   natural 64-bit snapshots/writes and byte strobes, while preserving 32-bit
   register accesses and response stability under backpressure.

Pre-fix failing sources/traces are retained under `out/negative_controls/`.

## Remaining profile work

Broader architectural/differential coverage, concurrent-agent memory ordering,
broader Zkt/Zvkt timing-contract evidence and a renewed full RV32 release audit
remain required. Native guest partial-vector-fault restart now covers nonadjacent
G-stage permissions and preservation of completed elements; full architectural
and concurrent-agent ordering verification remains separate.
Linux boot, a complete platform specification and synthesis timing closure are
separate validations. Standard external Debug Module/JTAG remains separate
platform work; the existing native halt/drain/debug-AXI ports remain available.

Reference snapshots for privileged 1.13/H 1.0 are in
`out/rva23/hypervisor_spec`, pinned to the ISA manual 20240411 tag with hashes.
Licensed H opcode snapshots are in `config/hypervisor_opcode_tables`.
References: [H extension](https://docs.riscv.org/reference/isa/priv/hypervisor),
[RVA23 profile](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html).

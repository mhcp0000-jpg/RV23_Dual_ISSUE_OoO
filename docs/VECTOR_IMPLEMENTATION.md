# Vector implementation work

The active target is complete RVV 1.0 plus RVA23-required Zvfhmin, Zvbb and Zvkt.
The vector owner is now connected to the decoder, ROB-head result path, scalar
integer/FP register operands, vector CSRs and the shared physical memory/PTW
ports. HAS_V defaults on for RV64 and remains off in the explicit RV32 mode.
The 95-file main source lists include the vector implementation. This is not
complete RVA23 compliance; H/VS context integration remains outstanding.

- `rv_vector_decode_pkg.sv`: 391 disjoint V/Zvbb encoding forms, exact scalar
  integer/FP source and destination namespaces. All forms were assembled with
  GNU; 717 masked/unmasked vectors passed the RTL decoder.
- `rv_vector_integer_alu.sv`: one integer/fixed-point element, WIDTH8/16/32/64.
  Includes saturating/averaging/fractional math, all vxrm modes, multiply/divide,
  widening/narrowing and Zvbb operations. The unbounded Python integer oracle
  passed 258,432 math cases and 65,920 explicit unsupported-operation checks.
  Register grouping, masks, restart and permutations belong to the owner.
- Opcode snapshots and BSD license are under `config/vector_opcode_tables`.
  `scripts/gen_vector_decode.py` checks their hashes and regenerates the decoder.
- `rv_vector_config.sv`: VLEN128/ELEN64 configuration arithmetic, mandatory
  fractional LMUL/SEW combinations, AVL, keep-vl and vill behavior; 66,621
  directed cases passed.
- `rv_vector_register_file.sv`: 32 VLEN128 registers, per-operation source
  snapshot, element/group mapping and isolated mask writes. 16,384 mapping
  checks and in-place snapshot/mask ownership tests passed. Payload is not reset.

`rv_vector_engine.sv` uses VLEN128/ELEN64, serialized execution at ROB head, a
32-register vector file and a source snapshot. LMUL1/2/4/8 and required
fractional LMUL, vl/vtype/vstart/vxrm/vxsat, masks, undisturbed inactive/tail
elements, reductions and permutations are implemented. The integer owner
passed 733 instruction packets; the FP owner passed another 235 packets with
masked flags, reductions, scalar boxing, widening/narrowing and Zvfhmin.

The FP lane passed 101 GNU encoding forms: 42,101 exact valid cases and 31,889
illegal-context checks. Width-specific integer conversions passed 34,080 cases.
vfrec7/vfrsqrt7 passed 849,880 exact comparisons against independently compiled
Spike helpers, including every FP16 bit pattern. Provenance and licenses for
the selected helper reference and normative tables remain under config/ and tb/.

Memory elements use `rv23_hypervisor_memory_head` for byte prevalidation and
VS/G context. Unit,
stride, indexed, segmented, whole-register, mask and fault-only-first transfers
passed 9,100 standalone packets transferring 2,740 bytes in Bare/Sv39
modes. Tests check nonadjacent physical pages, W/D/invalid/PBMT faults, first
failing-byte tval, earlier completed elements, unchanged faulting load elements,
vstart replay and fault-only-first vl updates. Fields within a faulting segment
may be partially completed as RVV permits. Indexed-segment destination/index
overlap is rejected. SRAM accesses and naturally aligned device/ROM accesses
are supported, including PBMT IO as uncached complete-size transfers. Split
accesses entering IO are rejected before any part of that element. Naturally
aligned elements use one 8/16/32/64-bit physical request, with full-size PMP
validation; two individually permitted PMP regions cannot be combined into one
aligned access. Unaligned elements split only after every byte is validated.

The caller drains older LSU traffic and holds irreversible head ownership until
retirement or the accepted fault. mstatus.VS and FS permissions are decoded;
vector CSR writes commit through the CSR file, and partial vector state marks
VS Dirty even on a later memory fault. Native execution passed 733 integer,
235 FP and 8,660 Bare-memory packets on the same OoO SoC. Separate native ELFs
passed eleven precise illegal/CSR/VS/FS traps and Sv39 partial-state, W/PBMT,
fault-only-first and same-PC vstart replay checks. The native model also enables
H, including guest partial load/store G-stage faults and retained same-PC
vstart=2 restart. Paired cycle timing checked 84,348 probes across 231 forms; a
secret-dependent VCLZ early-exit mutation was rejected. See TIMING_CONTRACT.md
for the limits of that evidence. Complete architectural validation remains open.

The reference is the [RVV 1.0 specification](https://github.com/riscvarchive/riscv-v-spec/blob/v1.0/v-spec.adoc),
with the [RVA23 profile](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)
defining the mandatory extensions. Standalone component tests are not evidence
of architectural V implementation or complete profile compliance.

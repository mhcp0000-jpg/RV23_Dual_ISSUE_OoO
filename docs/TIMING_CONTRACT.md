# Zkt / Zvkt implementation evidence

This is a cycle-latency implementation audit with directed execution evidence.
It is not a formal noninterference proof, complete ISA validation, synthesis
sign-off or whole-system side-channel assessment. Memory and conditional
control flow are outside these directed arithmetic regions.

## Scalar paths

The scalar ALU is combinational behind the normal fixed pipeline/result slots.
The multiplier has two valid-controlled stages; advance and ready depend on
valid/ready/flush/ROB ownership, not operand values. Decode and compressed
expansion depend on instruction bits. There is no operand-zero completion or
operand-value instruction elimination on these covered paths. Divider and
floating arithmetic are outside the scalar Zkt subset.

`run_scalar_timing_integration.py` runs 16 functional ELF fixtures with identical
text bytes and control flow and different memory data. On the same H-enabled
RV64 OoO SoC it compares every measured instruction's relative retirement
cycle: 408 instructions per trace, covering base integer/W operations,
multiplication, implemented B operations, compressed arithmetic, and additional
Zicond/Zcb operations. The report also requires more than 100 measured PCs to
produce differing data results. No fixed IPC benchmark ELF is changed.

## Vector paths

The serialized vector owner iterates from vstart to the configured element
bound. Register/scalar arithmetic values select results, not loop termination.
Gather always enters its gather state, including out-of-range data indices.
Mask execution can change work, as permitted by the timing contract; carry and
merge mask data are consumed without skipping iterations. VF slides have a
fixed per-element control sequence. Other floating arithmetic and storage
operations are outside this paired test.

`run_vector_timing_checks.py` drives two architectural vector owners with
common instructions/configuration/control masks and different register/scalar
data. It checks request and response timing cycle by cycle. It covers 231 forms,
426 encoding variants and 84,348 paired probes over legal SEW/LMUL combinations,
zero/one/maximum VL and zero/all-ones/single-bit/random patterns. Carry/merge
mask data is varied separately from execution masks. Every covered form must
have at least one legal execution. The test also includes integer operations
outside the required Zvkt subset.

`run_vector_timing_negative.py` injects an operand-dependent early exit into a
copy of the vector engine. The original RTL is not modified. The same vectors
and testbench must reject the mutation. Its result remains an expected-failure
control, never a normal RTL PASS claim.

Content-bound reports are under `out/rva23/scalar_timing`,
`out/rva23/vector_timing` and `out/negative_controls/vector_timing`.
The integration audit also checks the instruction lists against the recorded
executions. It identifies 64 scalar mnemonics from the implemented Zkt subset
and Zicond, and 164 vector forms from the implemented Zvkt families, with 294
legal form/mask-encoding pairs. Scalar evidence is matched to disassembled ELF
encodings and retire records. Vector evidence is matched to hardware request
and completion records for legal encodings. The scalar entry interval is
checked against the instruction immediately before the measured region.
These counts describe instruction membership. Backpressure and system timing
remain outside the measured result.

Normative references:
[scalar Zkt](https://github.com/riscv/riscv-crypto/blob/main/doc/scalar/riscv-crypto-scalar-zkt.adoc),
[vector Zvkt](https://github.com/riscv/riscv-crypto/blob/main/doc/vector/riscv-crypto-vector-zvkt.adoc),
[Zicond timing requirement](https://docs.riscv.org/reference/isa/unpriv/zicond.html).

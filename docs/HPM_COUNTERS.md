# Zihpm / Sscofpmf event bank

`rv_hpm_counters.sv` is connected to committed CSRs, counter access permissions,
scountovf and LCOFI. RV64 defaults to four HPM counters; the legacy RV32
configuration retains zero HPM counters. Directed component, committed-CSR and
native HS/VS overflow tests are separate content-bound reports in out/rva23.
This is not full architectural or timing sign-off.

Four 64-bit counters are implemented, `mhpmcounter3` through `mhpmcounter6`.
Other HPM counters and event selectors are read-only zero. Event encodings
are platform-defined:

| Selector | Event increment |
|---|---|
| 0 | Disabled |
| 1 | One per cycle |
| 2 | Retired instruction count, zero through two per cycle |
| 3 | One per cycle with two retired instructions |
| 4 | One per cycle with no retired instructions |

`mhpmevent` supports sticky OF and MINH/SINH/UINH/VSINH/VUINH filters.
Filters use the actual execution mode, including the virtual bit; MPRV does
not change that mode. `mcountinhibit` independently stops each counter.
Hardware wrap sets OF and asserts LCOFIP when OF was clear. Counter and event
CSR writes do not create overflow requests. LCOFIP and OF are independently
cleared by software; a new hardware overflow wins over a simultaneous pending
bit write. Event 2 includes instructions that retire counter CSR accesses.

The requirements snapshot is
`out/rva23/hypervisor_spec/sscofpmf.adoc`, from the privileged 1.13 source tag.

`mcounteren`, `hcounteren`, and `scounteren` expose implemented counter bits.
Machine-denied accesses raise cause 2; HS-qualified guest denial raises 22.
`scountovf` masks individual bits by mcounteren and, for guests, hcounteren.
LCOFIP has one storage owner; MIP/SIP writes access that same pending bit.
The optional machine Smstateen bank is not added by this counter implementation.

The RV64 H/V SoC fixture in scripts/run_hpm_mode_filters.py measures two
retirement counters in M, HS, U, VS and VU. One counter selects only the
mode under test, and the other excludes that mode. The same instruction
sequence measures a delta of ten retirements and zero, respectively, in
each mode. The M trap handler checks the ECALL PC, cause and saved MPP/MPV.
The contract audit repeats the result comparison from the committed trace.

The same driver with --machine-overflow checks nondelegated cause 13 in
the RV64 SoC. The first wrap sets OF and LCOFIP while MIE is clear.
Enabling MIE lets the M handler run, clear LCOFIP and return with MRET.
A second hardware wrap leaves OF set and generates no new interrupt.
Clearing OF rearms the counter and the third wrap delivers another cause
13. The existing rv64_hpm_overflow.S fixture checks the delegated HS
handler and a VS-mode wrap that preempts the guest.

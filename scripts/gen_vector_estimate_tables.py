"""Emit the exact 7-bit lookup tables recorded from the normative RVV spec."""
import json
from sim_runner import ROOT,sha
folder=ROOT/'config/vector_estimates';record=json.loads((folder/'tables.json').read_text())
for source in record['sources']:
    if 'file' in source:assert sha(ROOT/source['file'])==source['sha256']
    if 'selected_reference_file' in source:
        assert sha(ROOT/source['selected_reference_file'])==source['selected_reference_sha256']
lines=['// Exact lookup values from RVV 1.0; see config/vector_estimates/tables.json.',
    'package rv_vector_estimate_tables_pkg;']
for key,name in [('vfrec7','RECIPROCAL'),('vfrsqrt7','RECIPROCAL_SQRT')]:
    values=record['tables'][key];assert len(values)==128
    lines.append(f'  localparam logic [6:0] {name}[128]=\'{{')
    for start in range(0,128,16):
        lines.append('    '+','.join(f"7'd{x}" for x in values[start:start+16])+(',' if start<112 else ''))
    lines.append('  };')
lines+=['endpackage',''];(ROOT/'rtl/backend/rv_vector_estimate_tables_pkg.sv').write_text('\n'.join(lines))
print('Generated normative RVV estimate lookup package')

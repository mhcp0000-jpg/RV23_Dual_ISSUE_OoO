from pathlib import Path
import os, sys, json
from pyslang import DiagnosticEngine
from pyslang.ast import Compilation
from pyslang.syntax import SyntaxTree
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
c=Compilation()
sources=Path('rtl/filelist.f').read_text().splitlines()
for path in sources+['tb/rv23_elab.sv']:
    c.addSyntaxTree(SyntaxTree.fromFile(path))
c.getRoot()
diagnostics=c.getAllDiagnostics()
errors=[d for d in diagnostics if d.isError()]
report=DiagnosticEngine.reportAll(c.sourceManager,diagnostics)
Path('out').mkdir(exist_ok=True)
Path('out/elaboration.log').write_text(report,encoding='utf-8')
result={'passed':not errors,'errors':len(errors),'diagnostics':len(diagnostics),
        'sources':len(sources),'configurations':['XLEN32','XLEN64'],
        'scope':'SystemVerilog parse and elaboration; no ISA compliance claim'}
Path('out/elaboration.json').write_text(json.dumps(result,indent=2))
if errors: print(report)
print(json.dumps(result))
sys.exit(bool(errors))

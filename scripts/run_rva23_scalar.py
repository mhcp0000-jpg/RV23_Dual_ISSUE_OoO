"""Run real RV64 OoO+cache integration; this is not full RVA23 sign-off."""
import json,csv
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

folder=ROOT/'out/rva23/scalar';folder.mkdir(parents=True,exist_ok=True)
vectors=json.loads((ROOT/'out/rva23/bitmanip/report.json').read_text());assert vectors['passed']
elf=ROOT/vectors['integration_elf'];assert sha(elf)==vectors['integration_elf_sha256']
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
params=['-GXLEN=64','-GHAS_V=1','-GHAS_MISALIGNED=1','-GHAS_D=1','-GHAS_ZFHMIN=1','-GHAS_ZFA=1','-GHAS_ZAWRS=1','-GHAS_ZIMOP=1','-GHAS_ZCMOP=1','-GHAS_ZCB=1','-GHAS_SVINVAL=1','-GHAS_SSNPM=1','-GHAS_CBO=1','-GHAS_A=1','-GHAS_B=1','-GHAS_ZICOND=1','-GHAS_SMODE=1','-GHAS_MMU=1']
rom='tb/fixtures/bootrom/bootrom_host_jump64.hex'
with Simulator() as sim:
    path=folder/'model.json'
    old=json.loads(path.read_text()) if path.exists() else None
    inputs=source_inputs(files)
    # Reuse the vector integration model only on an exact content match.
    candidate_path=ROOT/'out/rva23/vector_integration/model.json'
    if candidate_path.exists():
        candidate=json.loads(candidate_path.read_text())
        if candidate['inputs']==inputs and candidate['params']==params and sha(ROOT/candidate['binary'])==candidate['binary_sha256']:
            old=candidate;dump(path,old)
    if old and old['inputs']==inputs and old['params']==params and sha(ROOT/old['binary'])==old['binary_sha256']:
        model=old
    else:
        model=sim.build('rva23_scalar','rv32_program_tb',files,params);dump(path,model)
    trace=folder/'commit.csv'
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    assert 'ELF AXI readback PASS' in text and 'PASS rv32_program_tb' in text
    assert 'data=0x42323331' in text
    for p,h in inputs.items():assert sha(ROOT/p)==h,p
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    payload=[r for r in rows if int(r['pc'],16)>=0x80000000]
    assert payload and not any(r['trap']=='1' for r in payload)
    checks=[r for r in payload if int(r['instruction'],16) in {
        int(line.split()[-1],16) for line in (ROOT/'out/rva23/bitmanip/rv64_integration.S').read_text().splitlines()
        if line.startswith('.word ')}]
    assert len(checks)==vectors['integration_cases'],(len(checks),vectors['integration_cases'])
    report={'passed':True,'scope':'RV64 B/Zicond plus basic M/S/U integrated execution; other feature tests are separate and V/H remain incomplete',
        'model':model,'run':run,'elf':elf.relative_to(ROOT).as_posix(),'elf_sha256':sha(elf),
        'runtime_inputs':{rom:sha(ROOT/rom)},'trace_sha256':sha(trace),
        'payload_instructions':len(payload),'new_extension_retirements':len(checks)}
    dump(folder/'report.json',report)
    print('PASS RV64 integrated B/Zicond retirements',len(checks),'payload instructions',len(payload),flush=True)
    supervisor=folder/'supervisor.elf'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imfc_zicsr_zifencei','-mabi=lp64f',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld','sw/tests/rv64_supervisor.S','-o',supervisor],
        folder/'supervisor_compile.log',60)
    s_trace=folder/'supervisor_commit.csv'
    s_run,s_text=sim.run([ROOT/model['binary'],f'+elf={supervisor.relative_to(ROOT).as_posix()}',
        f'+trace_file={s_trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'supervisor_simulation.log',180)
    assert 'data=0x53555031' in s_text and 'PASS rv32_program_tb' in s_text
    with s_trace.open(newline='') as stream:s_rows=list(csv.DictReader(stream))
    traps=[r for r in s_rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[8,2],traps
    assert sum(int(r['instruction'],16)==0x10200073 for r in s_rows)>=2
    report['supervisor']={'passed':True,'elf':supervisor.relative_to(ROOT).as_posix(),'elf_sha256':sha(supervisor),
        'source_sha256':sha(ROOT/'sw/tests/rv64_supervisor.S'),'run':s_run,'trace_sha256':sha(s_trace),
        'traps':[{k:r[k] for k in ['pc','instruction','cause','tval']} for r in traps]}
    dump(folder/'report.json',report)
    print('PASS RV64 integrated M/S/U delegation, SRET, illegal U MRET, SFENCE and Sstc CSR access',flush=True)

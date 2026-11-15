"""Checkpoint for implemented RVA23 features; never a full-profile completion gate."""
import argparse,json,subprocess,sys
from sim_runner import ROOT,sha,dump,source_inputs
steps=['run_bitmanip_checks.py','run_compressed_profile_checks.py',
    'run_supervisor_csr.py','run_mmu_checks.py','run_exclusive_checks.py',
    'run_atomic_engine_checks.py','run_wait_reservation_checks.py','run_cbo_head_checks.py',
    'run_rva23_scalar.py','run_sv39_integration.py','run_svinval_integration.py',
    'run_atomic_integration.py','run_atomic_sv39_integration.py',
    'run_profile_scalar_integration.py','run_pointer_mask_integration.py',
    'run_cbo_integration.py','run_cbo_sv39_integration.py',
    'run_compressed_d_checks.py','run_fp_format_checks.py','run_fp_aux_checks.py',
    'run_fpu_rva23_checks.py','run_fp_integration.py','run_fp_state_integration.py',
    'run_fp_sv39_integration.py','run_misaligned_head_checks.py',
    'run_misaligned_integration.py','run_misaligned_sv39_integration.py',
    'run_vector_decode_checks.py','run_vector_integer_checks.py','run_vector_config_checks.py','run_vector_register_checks.py',
    'run_vector_estimate_checks.py','run_vector_fp_integer_checks.py','run_vector_fp_lane_checks.py',
    'run_vector_integer_engine_checks.py','run_vector_fp_engine_checks.py','run_memory_element_checks.py','run_vector_memory_engine_checks.py',
    'run_vector_integration.py','run_vector_state_integration.py','run_vector_sv39_integration.py','audit_vector_components.py','audit_vector_integration.py',
    'run_hypervisor_decode_checks.py','run_hypervisor_stateen_checks.py','run_hypervisor_csr_checks.py',
    'run_hypervisor_csr_file_checks.py','run_hypervisor_memory_head_checks.py',
    'run_if_translation_checks.py','run_fetch_guest_metadata_checks.py','run_hpm_counter_checks.py','run_hpm_csr_file_checks.py',
    'run_elf_loader_checks.py','run_fetch_fault_decode_checks.py','run_hypervisor_integration.py','run_hypervisor_gstage_integration.py',
    'run_hypervisor_interrupt_integration.py','run_hypervisor_access_integration.py','run_hypervisor_vector_faults.py',
    'run_hpm_integration.py','run_privileged_instruction_matrix.py','run_hypervisor_breakpoint_metadata.py','audit_hypervisor_integration.py',
    'run_upstream_riscv_tests.py','audit_upstream_riscv_tests.py','run_upstream_privileged_tests.py','run_scalar_timing_integration.py',
    'run_vector_timing_checks.py','run_vector_timing_negative.py','audit_timing_contract.py']
report={'passed':False,'scope':'Current scalar/vector/H/Sha/HPM/privileged/MMU/cache and directed timing implementation checkpoint',
    'incomplete':['full architectural/differential verification','complete memory-ordering and timing-contract coverage',
                  'renewed full RV32 release audit'],
    'source_sha256':source_inputs((ROOT/'rtl/filelist.f').read_text().splitlines()),'steps':[]}
path=ROOT/'out/rva23/functional_checkpoint.json'
parser=argparse.ArgumentParser()
parser.add_argument('--resume',action='store_true')
args=parser.parse_args()
if args.resume and path.exists():
    previous=json.loads(path.read_text(encoding='utf-8'))
    if previous.get('source_sha256')==report['source_sha256']:
        for script,entry in zip(steps,previous.get('steps',[])):
            if not (entry['script']==script and entry['passed'] and
                    entry['sha256']==sha(ROOT/'scripts'/script)):break
            report['steps'].append(entry)
        print('REUSE current-source completed prefix:',len(report['steps']),'steps',flush=True)
try:
    for script in steps[len(report['steps']):]:
        print('RUN',script,flush=True)
        subprocess.run([sys.executable,str(ROOT/'scripts'/script)],cwd=ROOT,check=True)
        report['steps'].append({'script':script,'sha256':sha(ROOT/'scripts'/script),'passed':True})
        dump(path,report)
    for p,h in report['source_sha256'].items():assert sha(ROOT/p)==h,p
    report['passed']=True
finally:dump(path,report)
print('PASS implemented-feature checkpoint; full RVA23S64 implementation remains incomplete',flush=True)

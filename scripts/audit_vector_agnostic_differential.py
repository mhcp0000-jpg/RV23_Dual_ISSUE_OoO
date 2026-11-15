"""Recheck VTA/VMA values, unchanged program payloads and policy controls."""
import json
import struct
import subprocess
import sys
from collections import Counter

from sim_runner import ROOT,dump,sha
from run_sail_event_comparison import normalize,read_csv
from vector_agnostic_policy import snapshots,validate,validate_transition,compare_snapshots


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def segments(path):
    data=path.read_bytes()
    assert data[:6]==b'\x7fELF\x02\x01'
    entry,offset=struct.unpack_from('<QQ',data,24)
    size,count=struct.unpack_from('<HH',data,54)
    assert entry==0x80000000
    result=[]
    for i in range(count):
        kind,flags,start,va,pa,filesz,memsz,alignment=struct.unpack_from('<IIQQQQQQ',data,offset+i*size)
        if kind==1:
            assert 0x80000000<=pa and pa+memsz<=0x80100000
            result.append((flags,va,pa,memsz,alignment,data[start:start+filesz]))
    return result


def main():
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/audit_vector_state_differential.py')],cwd=ROOT,check=True)
    folder=ROOT/'out/rva23/vector_agnostic_differential'
    report=read(folder/'report.json')
    assert report['passed'] and not report['complete_profile_validation']
    assert report['generator_sha256']==sha(ROOT/'scripts/run_vector_agnostic_differential.py')
    base_path=ROOT/'out/rva23/vector_state_differential/report.json'
    ref_path=ROOT/'out/reference/sail-event-driver/report.json'
    assert report['base_report_sha256']==sha(base_path) and report['reference_report_sha256']==sha(ref_path)
    base,reference=read(base_path),read(ref_path)
    for p,h in {**report['inputs'],**base['model']['inputs'],**reference['inputs']}.items():
        assert sha(ROOT/p)==h,p
    for model in [base['model'],reference]:
        assert sha(ROOT/model['binary'])==model['binary_sha256']
    base_cases={c['name']:c for c in base['cases']}
    expected={(policy,name) for policy in ['ta_mu','tu_ma','ta_ma'] for name in base_cases}
    assert len(report['cases'])==len(report['selected'])==len(expected)==66
    assert {(c['policy'],c['base_name']) for c in report['cases']}==expected
    assert {(c['policy'],c['base_name']) for c in report['selected']}==expected
    words=events=differences=allowed_controls=rejected_controls=0
    total_coverage=Counter()
    changed_instructions=0
    for case in report['cases']:
        assert case['passed']
        original=base_cases[case['base_name']]
        ta,ma={'ta_mu':(1,0),'tu_ma':(0,1),'ta_ma':(1,1)}[case['policy']]
        assert (case['ta'],case['ma'])==(ta,ma)
        for key in ['sew','lmul','vlmax','vxrm','load_pc']:
            assert case[key]==original[key]
        assert case['vtype']==original['vtype']|(ta<<6)|(ma<<7)
        dest=folder/case['name']
        base_dest=ROOT/'out/rva23/vector_state_differential'/case['base_name']
        assert read(dest/'report.json')==case
        for filename,key in [('test.S','source'),('test.elf','elf'),('sail_events.csv','sail_trace'),('commit.csv','rtl_trace')]:
            assert sha(dest/filename)==case[key+'_sha256']
        replacement=','+('ta' if ta else 'tu')+','+('ma' if ma else 'mu')
        assert (dest/'test.S').read_text(encoding='utf-8')==(base_dest/'test.S').read_text(encoding='utf-8').replace(',tu,mu',replacement)
        before,after=segments(base_dest/'test.elf'),segments(dest/'test.elf')
        assert len(before)==len(after)
        changed=0
        for a,b in zip(before,after):
            assert a[:-1]==b[:-1] and len(a[-1])==len(b[-1])
            if a[0]&1:
                assert len(a[-1])%4==0
                for i in range(0,len(a[-1]),4):
                    old=int.from_bytes(a[-1][i:i+4],'little')
                    new=int.from_bytes(b[-1][i:i+4],'little')
                    if old!=new:
                        assert old&0x7f==0x57 and (old>>12)&7==7
                        assert old^new==((ta<<6)|(ma<<7))<<20
                        changed+=1
            else:
                assert a[-1]==b[-1]
        assert changed==5
        changed_instructions+=changed
        for phase in ['compile','sail','run']:
            run=case[phase]
            assert run['passed'] and run['exit_code']==0 and sha(ROOT/run['log'])==run['log_sha256']
        left,right=read_csv(dest/'sail_events.csv'),read_csv(dest/'commit.csv')
        left_states,right_states=snapshots(left,case['load_pc']),snapshots(right,case['load_pc'])
        for states,key in [(left_states,'sail_policy_coverage'),(right_states,'rtl_policy_coverage')]:
            coverage=validate(case,states)
            assert coverage==case[key]
        total_coverage.update(case['rtl_policy_coverage'])
        count,diff=compare_snapshots(left,right,case['load_pc'],normalize)
        assert count==case['compared'] and diff==case['permitted_word_differences']
        observed={address:[] for address in ['c20','c21','008','00a','009','00f','c22']}
        for row in left:
            instruction=int(row['instruction'],16);address=f'{instruction>>20:03x}'
            if instruction&0x7f==0x73 and row['rd']=='13' and address in observed:
                observed[address].append(int(row['wdata'],16))
        expected_csrs=dict(original['csr_snapshots'])
        expected_csrs['c21']=[case['vtype']]*5
        assert observed==case['csr_snapshots']==expected_csrs
        if case['name']=='ta_ma/e8_mf8':
            assert {c['name'] for c in case['policy_controls']}=={'allowed_tail','bad_tail','bad_prestart','bad_active','bad_vl_zero'}
            for control in case['policy_controls']:
                artifact=ROOT/control['artifact']
                assert sha(artifact)==control['sha256']
                error=None
                try:validate_transition(case,control['stage'],right_states[control['stage']-1],artifact.read_bytes())
                except ValueError as exception:error=str(exception)
                assert (error is None)==control['accepted'] and error==control['error']
                if control['accepted']:allowed_controls+=1
                else:
                    assert control['category'] in error
                    rejected_controls+=1
            allowed=case['allowed_choice_control']
            assert allowed['accepted'] and sha(ROOT/allowed['artifact'])==allowed['sha256']
            forked=read_csv(ROOT/allowed['artifact'])
            validate(case,snapshots(forked,case['load_pc']))
            fork_count,fork_diff=compare_snapshots(forked,right,case['load_pc'],normalize)
            assert fork_count==count and fork_diff==allowed['permitted_word_differences']==4
            allowed_controls+=1
        words+=case['snapshot_words'];events+=count;differences+=diff
    assert words==report['snapshot_words']==21120 and events==report['events_compared']==116754
    assert (allowed_controls,rejected_controls)==(2,4)
    assert all(total_coverage[k]>0 for k in ['active','prestart','tail_agnostic','mask_agnostic','tail_undisturbed','mask_undisturbed','vl_zero'])
    dump(folder/'audit.json',dict(passed=True,complete_profile_validation=False,scope=report['scope'],
        audit_sha256=sha(__file__),report_sha256=sha(folder/'report.json'),cases=66,checkpoints=330,
        vector_words_checked=words,csr_values_checked=2310,events_compared=events,
        permitted_word_differences=differences,policy_bits_only_instruction_changes=changed_instructions,
        policy_coverage=dict(total_coverage),accepted_controls=allowed_controls,rejected_controls=rejected_controls))
    print('PASS current vector agnostic audit: 66 cases, 21120 vector words, 2 accepted and 4 rejected controls')


if __name__=='__main__':main()

"""Recompare complete register/CSR snapshots for all 22 tested vector types."""
import json

from audit_sail_event_comparison import verify_reference_driver
from sim_runner import ROOT, dump, sha, source_inputs
from run_sail_event_comparison import compare, read_csv


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def main():
    folder=ROOT/'out/rva23/vector_state_differential'
    report=read(folder/'report.json')
    assert report['passed'] and not report['complete_profile_validation']
    assert report['generator_sha256']==sha(ROOT/'scripts/run_vector_state_differential.py')
    reference_path=ROOT/'out/reference/sail-event-driver/report.json'
    assert report['reference_report_sha256']==sha(reference_path)
    verify_reference_driver()
    files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    assert report['model']['inputs']==source_inputs(files)
    for p,h in report['runtime_inputs'].items():
        assert sha(ROOT/p)==h,p
    model = report['model']
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    config=read(ROOT/'config/reference/sail-rv23.json')
    assert config['extensions']['V']['vlen_exp']==7 and config['extensions']['V']['elen_exp']==6
    expected={(sew,lmul) for sew in [8,16,32,64] for lmul,n,d in [
        ('mf8',1,8),('mf4',1,4),('mf2',1,2),('m1',1,1),('m2',2,1),('m4',4,1),('m8',8,1)] if sew*d<=64*n}
    assert len(report['selected'])==len(report['cases'])==len(expected)==22
    assert {(c['sew'],c['lmul']) for c in report['selected']}==expected
    assert {(c['sew'],c['lmul']) for c in report['cases']}==expected
    assert {c['vxrm'] for c in report['cases']}=={0,1,2,3}
    count=words=negative_controls=0
    for case in report['cases']:
        assert case['passed'] and case['snapshots']==5 and case['snapshot_words']==320
        dest=folder/case['name']
        assert read(dest/'report.json')==case
        for filename,key in [('test.S','source'),('test.elf','elf'),('sail_events.csv','sail_trace'),('commit.csv','rtl_trace')]:
            assert sha(dest/filename)==case[key+'_sha256']
        for phase in ['compile','sail','run']:
            run=case[phase]
            assert run['passed'] and run['exit_code']==0
            assert sha(ROOT/run['log'])==run['log_sha256']
        left,right=read_csv(dest/'sail_events.csv'),read_csv(dest/'commit.csv')
        compared,mismatch=compare(left,right)
        assert mismatch is None and compared==case['compared']
        snapshots=[r for r in left if int(r['pc'],16)==case['load_pc']]
        actual=[r for r in right if int(r['pc'],16)==case['load_pc']]
        assert len(snapshots)==len(actual)==320
        assert [r['wdata'] for r in snapshots]==[r['wdata'] for r in actual]
        assert len({r['wdata'] for r in snapshots})>32
        assert sum(int(r['instruction'],16)&0x7f==0x27 for r in left)==160
        assert sum(int(r['instruction'],16)&0x7f==0x07 for r in left)==32
        expected_csrs={'c20':[case['vlmax'],case['vlmax'],case['vlmax']-1,0,case['vlmax']],
            'c21':[case['vtype']]*5,'008':[0]*5,'00a':[case['vxrm']]*5,
            '009':[0,0,1,1,1],'00f':[(case['vxrm']<<1)|v for v in [0,0,1,1,1]],'c22':[16]*5}
        observed={address:[] for address in expected_csrs}
        for row in left:
            instruction=int(row['instruction'],16)
            address=f'{instruction>>20:03x}'
            if instruction&0x7f==0x73 and row['rd']=='13' and address in observed:
                observed[address].append(int(row['wdata'],16))
        assert observed==case['csr_snapshots']==expected_csrs
        if case['name']=='e8_mf8':
            negative=case['negative_control']
            assert negative['rejected']
            corrupted_path=dest/'corrupted_vector_word.csv'
            assert sha(corrupted_path)==negative['trace_sha256']
            corrupted=read_csv(corrupted_path)
            index=negative['index']
            assert len(corrupted)==len(left) and int(left[index]['pc'],16)==case['load_pc']
            fixed=[dict(r) for r in corrupted]
            assert int(fixed[index]['wdata'],16)^int(left[index]['wdata'],16)==1<<63
            fixed[index]['wdata']=left[index]['wdata']
            assert fixed==left
            bad_index,bad=compare(corrupted,right)
            assert bad is not None and bad_index==index and bad==negative['mismatch']
            negative_controls+=1
        count+=compared;words+=len(snapshots)
    assert words==report['snapshot_words']==7040 and count==report['events_compared']==38918
    assert negative_controls==1
    dump(folder/'audit.json',dict(passed=True,complete_profile_validation=False,scope=report['scope'],
        audit_sha256=sha(__file__),report_sha256=sha(folder/'report.json'),
        configurations=22,checkpoints=110,vector_words_compared=words,
        csr_values_compared=770,events_compared=count,high_bit_negative_controls=negative_controls))
    print('PASS current vector state audit: 22 configurations, 7040 vector words, 770 CSR values, 38918 events')


if __name__=='__main__':
    main()

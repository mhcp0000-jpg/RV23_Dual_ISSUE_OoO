"""Validate the mandatory-requirement review queue, never certify ISA compliance."""
import argparse
import copy
import json
from pathlib import PurePosixPath

from sim_runner import ROOT, dump, sha, source_inputs

INDEX = 'config/rva23_clause_review_index.json'
INVENTORY = 'config/rva23_required_extensions.json'
MAP = 'config/rva23_implementation_map.json'
GUIDE = 'docs/RVA23_REMAINING_REVIEW.md'


def required_names(inventory):
    return {'I', *inventory['mandatory_unprivileged_inherited_from_RVA23U64'],
        *inventory['mandatory_unprivileged_added_by_RVA23S64'],
        *inventory['mandatory_supervisor'], *inventory['Sha_components']}


def validate(index, inventory, implementation):
    assert index['profile'] == inventory['profile'] == implementation['profile'] == 'RVA23S64'
    assert index['complete_profile_validation'] is False
    required = required_names(inventory)
    assert len(required) == 59
    groups, seen, ids, item_ids, documents = index['groups'], set(), set(), set(), set()
    resolved_ids, closure_inputs = set(), set()
    expected_groups = {frozenset(['I']), *(frozenset(group['requirements']) for group in implementation['groups'])}
    assert len(groups) == len(expected_groups) == 22
    actual_groups = set()
    for group in groups:
        assert group['id'] and group['id'] not in ids and group['title']
        ids.add(group['id'])
        names = group['requirements']
        assert names and len(names) == len(set(names)) and not seen.intersection(names)
        seen.update(names)
        actual_groups.add(frozenset(names))
        assert group['review_status'] == ('partial' if group['open_items'] else 'reviewed')
        assert group['reviews'] and len(group['reviews']) == len(set(group['reviews']))
        for name in group['reviews']:
            path = PurePosixPath(name)
            assert path.parts[0] == 'docs' and '..' not in path.parts and path.suffix == '.md'
            text = (ROOT / name).read_text(encoding='utf-8')
            assert text.startswith('# ') and len(text) > 200, name
            documents.add(name)
        for item in group['open_items']:
            assert item['id'].startswith(group['id'] + '.') and item['id'] not in item_ids
            assert len(item['topic']) > 30
            item_ids.add(item['id'])
        resolved = group.get('resolved_items', [])
        assert group['open_items'] or resolved, 'Reviewed group needs a disposition record'
        for item in resolved:
            assert item['id'].startswith(group['id'] + '.') and item['id'] not in resolved_ids
            assert item['id'] not in item_ids and len(item['topic']) > 30 and len(item['disposition']) > 60
            assert item['review_document'] in group['reviews']
            assert item['checks'] and item['reports'] and item['source_paths']
            assert all(PurePosixPath(name).name == name for name in item['checks'])
            drivers = [ROOT / 'scripts' / name for name in item['checks']]
            assert all(path.is_file() and path.suffix == '.py' for path in drivers)
            for name in item['source_paths']:
                path = PurePosixPath(name)
                assert path.parts[0] in ('rtl', 'scripts', 'docs') and '..' not in path.parts
                assert (ROOT / name).is_file()
                closure_inputs.add(name)
            for name in item['reports']:
                path = PurePosixPath(name)
                assert path.parts[0] == 'out' and '..' not in path.parts and path.suffix == '.json'
                report = json.loads((ROOT / name).read_bytes())
                producer = report.get('generator_sha256', report.get('driver_sha256', report.get('audit_sha256')))
                assert report['passed'] and producer in {sha(driver) for driver in drivers}
                closure_inputs.add(name)
            closure_inputs.update('scripts/' + name for name in item['checks'])
            resolved_ids.add(item['id'])
    assert seen == required and actual_groups == expected_groups, sorted(required - seen)
    assert not resolved_ids.intersection(item_ids)
    return dict(requirements=len(seen), groups=len(groups), partial_groups=sum(bool(g['open_items']) for g in groups),
        reviewed_groups=sum(not g['open_items'] for g in groups), open_items=len(item_ids), resolved_items=len(resolved_ids),
        documents=sorted(documents), closure_inputs=sorted(closure_inputs))


def render(index):
    groups = index['groups']
    count = sum(len(group['open_items']) for group in groups)
    lines = ['# RVA23S64 남은 규격 검토', '',
        '이 문서는 `config/rva23_clause_review_index.json`에서 생성한 검토 작업 목록이다.',
        f'RV64I와 필수 확장 58개를 포함한 59개 요구사항, {len(groups)}개 구현 그룹과',
        f'{count}개 미완료 검토 주제를 연결한다. 이는 결함 {count}개라는 뜻이 아니다.',
        '또한 완전한 규격 조항 목록이나 구현·검증 완료 판정표가 아니다.', '',
        '각 주제를 닫을 때는 규격 조항, 실제 RTL 경로, 실행·예외·상태·순서의 근거와',
        '허용된 구현 선택을 해당 검토 문서에 남긴다. 새 실패가 있으면 RTL 수정과',
        '원래 실패를 재현하는 검사 및 관련 회귀를 완료한다. 구현 선택으로 충족하면',
        '그 이유를 기록한다. 단순 테스트 개수나 확장 이름으로 종료하지 않는다.', '',
        '인덱스 검사는 요구사항 누락·중복, 문서 연결, 상태 일관성과 현재 파일 해시를',
        '확인한다. 검토 내용의 논리적 충분성을 자동으로 판정하지 않는다. 모든 작업이',
        '목록에서 사라져도 이 검사만으로 전체 프로파일 달성을 선언할 수 없다.', '',
        '| 그룹 | 요구사항 | 열린 주제 | 현재 검토 |', '|---|---|---:|---|']
    for group in groups:
        reviews = ', '.join(f'[{PurePosixPath(name).name}]({PurePosixPath(name).name})' for name in group['reviews'])
        lines.append(f"| {group['id']} | {', '.join(group['requirements'])} | {len(group['open_items'])} | {reviews} |")
    for group in groups:
        lines += ['', f"## {group['id']}: {group['title']}", '']
        if not group['open_items']:
            lines.append('이 작업 목록에 남은 검토 주제 없음. 연결 문서의 실제 근거와 한계를 확인한다.')
            lines.append('')
        for item in group['open_items']:
            lines.append(f"- [ ] `{item['id']}` — {item['topic']}")
        for item in group.get('resolved_items', []):
            name = PurePosixPath(item['review_document']).name
            lines += [f"- [x] `{item['id']}` — {item['topic']}", '',
                f"검토 결론: {item['disposition']}", '', f'근거: [{name}]({name})', '']
    lines += ['', '## 갱신·재검사', '', '```text',
        'python scripts/audit_clause_review_index.py --write',
        'python scripts/audit_clause_review_index.py',
        'python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm',
        '```', '', '검토 내용은 인덱스와 연결 문서를 함께 수정하고 첫 명령으로 이 문서를 갱신한다.',
        '보고서는 `out/rva23/clause_review_index_audit.json`에 있으며 전체 목표는 활성 상태다.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='Regenerate the human-readable review queue')
    args = parser.parse_args()
    read = lambda name: json.loads((ROOT / name).read_bytes())
    index, inventory, implementation = read(INDEX), read(INVENTORY), read(MAP)
    result = validate(index, inventory, implementation)
    guide = render(index)
    if args.write:
        (ROOT / GUIDE).write_text(guide, encoding='utf-8')
    assert (ROOT / GUIDE).read_text(encoding='utf-8') == guide, 'Review guide is stale; regenerate with --write'
    controls = []
    mutations = ['missing_requirement', 'missing_group', 'duplicate_requirement', 'false_reviewed', 'missing_document', 'unjustified_reviewed']
    if any(group.get('resolved_items') for group in index['groups']):
        mutations += ['missing_closure_evidence', 'wrong_closure_driver']
    for name in mutations:
        broken = copy.deepcopy(index)
        if name == 'missing_requirement':
            broken['groups'][1]['requirements'].pop()
        elif name == 'missing_group':
            broken['groups'].pop()
        elif name == 'duplicate_requirement':
            broken['groups'][1]['requirements'].append('I')
        elif name == 'false_reviewed':
            broken['groups'][0]['review_status'] = 'reviewed'
        elif name == 'missing_document':
            broken['groups'][0]['reviews'] = ['docs/missing_clause_review.md']
        elif name == 'unjustified_reviewed':
            broken['groups'][0].update(open_items=[], review_status='reviewed', resolved_items=[])
        else:
            closed = next(group for group in broken['groups'] if group.get('resolved_items'))['resolved_items'][0]
            if name == 'missing_closure_evidence':
                closed['reports'] = []
            else:
                closed['checks'] = ['audit_clause_review_index.py']
        try:
            validate(broken, inventory, implementation)
        except (AssertionError, FileNotFoundError):
            controls.append(name)
        else:
            raise AssertionError(f'Invalid review queue accepted: {name}')
    inputs = source_inputs([INDEX, INVENTORY, MAP, GUIDE, 'scripts/audit_clause_review_index.py', 'scripts/sim_runner.py',
        *result['documents'], *result['closure_inputs']])
    dump(ROOT / 'out/rva23/clause_review_index_audit.json', dict(passed=True, complete_profile_validation=False,
        scope='Review queue integrity and current document hashes only; not exhaustive clause inventory, functional execution or architectural proof',
        **result, inputs=inputs, rejected_mutations=controls, audit_sha256=sha(__file__),
        open_work={g['id']: g['open_items'] for g in index['groups'] if g['open_items']}))
    print('PASS review queue:', result['requirements'], 'requirements;', result['groups'], 'groups;',
        result['open_items'], 'open review items;', len(controls), 'rejected integrity mutations; no architectural completion claim', flush=True)


if __name__ == '__main__':
    main()

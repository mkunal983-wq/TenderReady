"""Read the retained UI scenario over HTTP and independently confirm SQLite records.

Does not insert fixtures or modify application data. Exports/report are local deliverables.
"""
import csv
import io
import json
from pathlib import Path
import httpx
from sqlalchemy import select
from tenderready.config import Settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import CorrectiveTask, TaskEvent, ReviewDecision


def main():
    settings = Settings()
    token = settings.app_api_token.get_secret_value()
    output = Path(__file__).resolve().parents[2]
    with httpx.Client(base_url='http://127.0.0.1:8000', headers={'Authorization': f'Bearer {token}'} if token else {}) as client:
        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response
        workspace = next(w for w in get('/workspaces').json() if w['title'] == 'Amendment UI demo — RAM 16 to 32 GB')
        prefix = '/workspaces/' + workspace['id']
        data = get(prefix + '/dashboard').json()
        assert not data['review_complete'] and data['counts']['conflicting'] == 1
        assert sum(data['counts'].values()) == 2
        ram = next(r for r in data['requirements'] if r['clause_id'] == 'ram-01')
        ssd = next(r for r in data['requirements'] if r['clause_id'] == 'ssd-01')
        assert ram['assessment']['review_state'] == 'approved' and ram['status'] == 'conflicting'
        assert ssd['assessment']['review_state'] == 'approved' and not ssd['assessment']['stale']
        assert ssd['status'] == 'inconclusive' and ssd['obligation'] == 'unclear'
        task = next(t for t in data['tasks'] if t['assessment_id'] == ram['assessment']['id'])
        assert task['priority'] == 'high' and task['due_date'] == '2026-11-01'
        assert task['status'] == 'open' and task['revision'] >= 3
        assert len(task['history']) >= 2
        timeline = get(prefix + '/timeline?limit=100').json()
        assert any(e['kind'] == 'reassessment' for e in timeline['items'])
        creation = next(e for e in timeline['items'] if e['kind'] == 'task')
        assert creation['description'] == 'Resolve evidence finding: Conflict detected'
        for r in data['requirements']:
            detail = get(prefix + '/requirements/' + r['requirement_id'] + '/detail').json()
            assert detail['page'] == 1 and detail['history']
            assert get(prefix + '/documents/' + r['document_id'] + '/file').content.startswith(b'%PDF-')
        exports = {}
        for kind in ('compliance-matrix', 'evidence-index'):
            response = get(prefix + '/exports/' + kind)
            rows = list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
            assert rows[0]['record_type'] == 'workspace_summary' and rows[0]['unresolved'] == 'True'
            assert 'Conflict detected' in response.text and '32 GB' in response.text if kind == 'compliance-matrix' else 'RAM: 16 GB' in response.text
            assert 'storage_key' not in response.text
            (output / (kind + '.csv')).write_bytes(response.content)
            exports[kind] = {'data_rows': len(rows) - 1, 'status': response.status_code}
    engine = build_engine(settings.database_url)
    with build_session_factory(engine)() as db:
        persisted = db.get(CorrectiveTask, task['id'])
        assert persisted.priority == 'high' and persisted.due_date == '2026-11-01' and persisted.revision == task['revision']
        events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == task['id'])))
        assert len(events) == len(task['history'])
        reviews = list(db.scalars(select(ReviewDecision).where(ReviewDecision.assessment_id == ram['assessment']['id'])))
        assert any(r.reviewer == 'Synthetic UI reviewer' and r.action == 'approved' for r in reviews)
    engine.dispose()
    report = {'result': 'passed', 'workspace_id': workspace['id'], 'snapshot': data['snapshot_sequence'],
        'counts': data['counts'], 'review_complete': data['review_complete'], 'blockers': data['blockers'],
        'ram_finding': ram['status'], 'ram_review': ram['assessment']['review_state'],
        'ssd_approval_preserved': True, 'ssd_needs_review_reason': 'Mandatory/optional obligation is unclear.',
        'task_id': task['id'], 'task_revision': task['revision'], 'task_priority': task['priority'],
        'task_due_date': task['due_date'], 'task_audit_events': len(events), 'timeline_events': timeline['total'],
        'exports': exports, 'independent_database_read': 'passed', 'live_inference': 'not run; key pending',
        'data_origin': 'Existing synthetic PDF scenario, real HTTP API and persisted database; no mock responses.'}
    (output / 'supplier-demo-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

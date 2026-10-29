"""Real migrated database, source PDFs, approvals, task audit and protected CSV exports."""
import csv
import io
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tenderready.api import create_app
from tenderready.models import RequirementVersion, SourceSpan, TaskEvent, CorrectiveTask
from tenderready.supplier import effective_status, csv_cell
from test_documents import config, workspace
from test_verification import send_pdf, pdf, evaluate
from test_amendments import setup, upload_revision, apply, RAM32, AUTH


@pytest.mark.parametrize('status,review,stale,obligation,expected', [
    ('supported','approved',False,'mandatory','supported'),
    ('supported','awaiting_review',False,'mandatory','inconclusive'),
    ('supported','rejected',False,'mandatory','inconclusive'),
    ('supported','reopened',False,'mandatory','inconclusive'),
    ('supported','approved',True,'mandatory','inconclusive'),
    ('supported','approved',False,'unclear','inconclusive'),
    ('missing','approved',False,'mandatory','missing'),
    ('conflicting','approved',False,'mandatory','conflicting'),
    ('outdated','approved',False,'mandatory','outdated'),
    ('inconclusive','approved',False,'mandatory','inconclusive'),
])
def test_readiness_status_gate(status,review,stale,obligation,expected):
    assert effective_status(dict(status=status, review_state=review, stale=stale, explanation='finding'), obligation)[0] == expected


def make_mandatory(client, sessions, obligation="mandatory"):
    wid = workspace(client)
    text = 'Model: Atlas A14\nRAM: at least 16 GB'
    doc = send_pdf(client,wid,pdf(f'The following requirements are {obligation}.\n'+text))
    # Trusted fixture interpretation, stored with actual source. No mock API responses.
    with sessions() as db:
        span = db.scalar(select(SourceSpan).where(SourceSpan.document_version_id==doc['id']))
        req = RequirementVersion(workspace_id=wid,requirement_key=str(uuid4()),version=1,source_span_id=span.id,
            statement=text,category='numeric_threshold',obligation=obligation,condition={'excerpt':text})
        db.add(req);db.commit();rid=req.id
    send_pdf(client,wid,pdf('Model: Atlas A14\nRAM: 16 GB'),'datasheet')
    a = evaluate(client,wid,rid)
    assert client.post(f'/workspaces/{wid}/documents/{doc["id"]}/baseline',json=AUTH).status_code==201
    return wid,rid,a


def test_readiness_requires_current_approved_evidence_and_published_snapshot(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid,rid,a=make_mandatory(c,sessions);base=f'/workspaces/{wid}'
        assert not c.get(base+'/dashboard').json()['review_complete']
        decision={'action':'approved','reviewer':'QA reviewer','comment':'Inspected source and full scope.'}
        assert c.post(base+f'/assessments/{a["id"]}/reviews',json=decision).status_code==201
        data=c.get(base+'/dashboard').json()
        assert data['review_complete'] and data['counts']['supported']==1
        assert data['requirements'][0]['requirement_id']==rid
        assert c.get(base+f'/requirements/{rid}/detail').json()['history'][0]['reviews'][0]['comment']==decision['comment']
        send_pdf(c,wid,pdf('Review this revised tender before submission.'))
        data=c.get(base+'/dashboard').json()
        assert not data['review_complete'] and data['pending_documents']
        assert data['counts']['supported']==1  # Global pending amendment doesn't rewrite assessment.
        send_pdf(c,wid,pdf('Model: Atlas A14\nRAM: 8 GB'),'datasheet')
        assert c.get(base+'/dashboard').json()['counts']['inconclusive']==1
        assert c.post(base+f'/assessments/{a["id"]}/reviews',json=decision).status_code==409


def test_amendment_dashboard_history_and_csv_use_only_active_requirements(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid,_,_,_,_,_=setup(c);_,base=upload_revision(c,wid,RAM32);apply(c,base)
        prefix=f'/workspaces/{wid}'
        data=c.get(prefix+'/dashboard').json()
        assert sum(data['counts'].values())==2 and data['counts']['conflicting']==1
        assert not data['review_complete'] and len(data['requirements'])==2
        events=c.get(prefix+'/timeline?limit=100').json()
        assert {'review','snapshot','reassessment','change','document','task'} <= {e['kind'] for e in events['items']}
        assert all(e['created_at'].endswith('+00:00') for e in events['items'])
        assert len(c.get(prefix+'/timeline?limit=1&offset=1').json()['items'])==1
        for kind in ['compliance-matrix','evidence-index']:
            response=c.get(prefix+'/exports/'+kind)
            assert response.status_code==200 and response.headers['cache-control']=='no-store'
            assert 'attachment' in response.headers['content-disposition']
            assert 'storage_key' not in response.text
            rows=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
            assert rows[0]['record_type']=='workspace_summary' and rows[0]['unresolved']=='True'
            assert any('Conflict detected' in str(row) for row in rows)
            if kind=='compliance-matrix':
                assert len(rows)==3 and any('32 GB' in row['exact_clause'] for row in rows[1:])


TASK={'title':'Obtain corrected datasheet','explanation':'Ask the manufacturer for the correct model and upload the signed datasheet. Rerun RAM verification.',
      'priority':'high','due_date':'2026-11-01','reviewer':'QA reviewer','comment':'Evidence discrepancy needs resolution.'}


def test_task_updates_are_audited_and_do_not_establish_compliance(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid,_,_,_,assessments,_=setup(c);base=f'/workspaces/{wid}'
        response=c.post(base+'/tasks',json={**TASK,'assessment_id':assessments[0]['id']})
        assert response.status_code==201,response.text
        task=response.json();assert task['due_date']=='2026-11-01' and len(task['history'])==1
        payload={**TASK,'status':'resolved','expected_revision':1,'comment':'Uploaded corrected evidence; verification still required.'}
        r=c.post(base+'/tasks/'+task['id'],json=payload);assert r.status_code==200,r.text
        assert r.json()['revision']==2 and len(r.json()['history'])==2
        assert c.post(base+'/tasks/'+task['id'],json=payload).status_code==409
        assert not c.get(base+'/dashboard').json()['review_complete']
        for bad in [{'priority':'critical'},{'due_date':'tomorrow'},{'title':' '},{'unexpected':True}]:
            assert c.post(base+'/tasks',json={**TASK,'assessment_id':assessments[0]['id'],**bad}).status_code==422
        other=workspace(c)
        assert c.post(f'/workspaces/{other}/tasks',json={**TASK,'assessment_id':assessments[0]['id']}).status_code==404
        assert c.post(f'/workspaces/{other}/tasks/{task["id"]}',json=payload).status_code==404
        assert c.get(f'/workspaces/{other}/requirements/{task["requirement_id"]}/detail').status_code==404
        with sessions() as db:
            event=db.scalar(select(TaskEvent).where(TaskEvent.task_id==task['id']))
            with pytest.raises(IntegrityError):
                db.execute(update(TaskEvent).where(TaskEvent.id==event.id).values(comment='rewritten'))
            db.rollback()
            assert db.get(CorrectiveTask,task['id']).status=='resolved'


@pytest.mark.parametrize('value', ['=HYPERLINK("bad")','  +SUM(1,2)','-1+2','@formula','\ttext','\rtext','\ntext'])
def test_csv_formula_cells_are_escaped(value):
    assert csv_cell(value).startswith("'")


def test_exports_quote_multiline_clauses_and_formula_titles(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid=c.post('/workspaces',json={'title':'=HYPERLINK("unsafe")','supplier_name':'Supplier'}).json()['id']
        for kind in ['compliance-matrix','evidence-index']:
            rows=list(csv.DictReader(io.StringIO(c.get(f'/workspaces/{wid}/exports/{kind}').text.lstrip('\ufeff'))))
            assert any(value.startswith("'=HYPERLINK") for value in rows[0].values())


def test_supplier_endpoints_require_auth_and_trusted_origin(database,tmp_path):
    engine,_=database
    settings=config(tmp_path).model_copy(update={'app_api_token':__import__('pydantic').SecretStr('a'*40)})
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings,engine),client=('127.0.0.1',1)) as c:
        wid=str(uuid4());prefix=f'/workspaces/{wid}'
        for path in ['/dashboard','/timeline','/exports/compliance-matrix','/exports/evidence-index',f'/requirements/{uuid4()}/detail']:
            assert c.get(prefix+path).status_code==401
            assert c.get(prefix+path,headers={'Authorization':'Bearer '+'a'*40,'Origin':'https://untrusted.example'}).status_code==403
        assert c.post(prefix+'/tasks',json={**TASK,'assessment_id':str(uuid4())}).status_code==401
        assert c.post(prefix+f'/tasks/{uuid4()}',json={**TASK,'expected_revision':1,'status':'open'}).status_code==401


def test_empty_workspace_and_unknown_workspace(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid=workspace(c);d=c.get(f'/workspaces/{wid}/dashboard').json()
        assert not d['review_complete'] and d['requirements']==[] and sum(d['counts'].values())==0
        assert c.get(f'/workspaces/{uuid4()}/dashboard').status_code==404


def test_optional_issue_is_disclosed_without_claiming_it_is_supported(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid,_,_=make_mandatory(c,sessions,obligation="optional")
        data=c.get(f'/workspaces/{wid}/dashboard').json()
        assert not data['review_complete'] and data['counts']['inconclusive']==1
        assert data['requirements'][0]['unresolved'] and not data['requirements'][0]['blocking']


def test_open_task_blocks_mandatory_review_completion_until_resolved(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as c:
        wid,_,a=make_mandatory(c,sessions);base=f'/workspaces/{wid}'
        c.post(base+f'/assessments/{a["id"]}/reviews',json={'action':'approved','reviewer':'Reviewer','comment':'All criteria reviewed.'})
        task=c.post(base+'/tasks',json={**TASK,'assessment_id':a['id']}).json()
        assert not c.get(base+'/dashboard').json()['review_complete']
        result=c.post(base+'/tasks/'+task['id'],json={**TASK,'title':'Record complete','status':'resolved','expected_revision':1})
        assert result.status_code==200
        assert c.get(base+'/dashboard').json()['review_complete']
        creation=next(e for e in c.get(base+'/timeline?limit=100').json()['items'] if e['kind']=='task')
        assert creation['description']==TASK['title']  # Earlier history does not acquire the edited title.

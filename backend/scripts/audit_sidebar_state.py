"""Read back UI-created synthetic audit records; exercise rejected live requests. No mocks."""
import csv
import io
import json
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import select, func
from tenderready.config import Settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import DocumentVersion, Assessment, ReviewDecision, CorrectiveTask, TaskEvent

ROOT=Path(__file__).resolve().parents[2]
WID='7c673b59-42cd-4976-a2c8-b84784ec9191'


def main():
    settings=Settings()
    token=settings.app_api_token.get_secret_value()
    report={'workspace_id':WID,'data_kind':'Synthetic data created through actual browser UI','checks':{}}
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60,headers={'Authorization':f'Bearer {token}'} if token else {}) as client:
        prefix=f'/workspaces/{WID}'
        def get(path):
            response=client.get(path)
            response.raise_for_status()
            return response.json()
        report['nemotron']=get('/ready')['inference']
        docs=get(prefix+'/documents'); evidence=get(prefix+'/evidence'); snapshots=get(prefix+'/snapshots'); dashboard=get(prefix+'/dashboard')
        assert len(docs)==2 and len(evidence)==1 and len(snapshots)==2
        changed=next(c for c in snapshots[0]['changes'] if c['classification']=='Modified')
        unchanged=next(c for c in snapshots[0]['changes'] if c['classification']=='Unchanged')
        assert changed['after']['clause_id']=='ram-01' and unchanged['after']['clause_id']=='ssd-01'
        impact=changed['impacts'][0]
        assert impact['old_assessment']['review_state']=='reopened' and len(impact['old_assessment']['reviews'])>=5
        executed=[c['field'] for c in impact['new_assessment']['checks'] if c.get('execution')=='executed']
        assert executed==['ram_gb']
        ssd=next(r for r in snapshots[0]['requirements'] if r['clause_id']=='ssd-01')
        oldssd=next(r for r in snapshots[1]['requirements'] if r['clause_id']=='ssd-01')
        assert ssd['assessment']['id']==oldssd['assessment']['id'] and ssd['assessment']['review_state']=='approved' and not ssd['assessment']['stale']
        ram=next(r for r in dashboard['requirements'] if r['clause_id']=='ram-01')
        assert ram['status']=='conflicting' and not dashboard['review_complete']
        verification=get(prefix+f'/requirements/{ram["requirement_id"]}/verification')
        assert verification['assessments'][0]['checks'][0]['method']=='human_correction'
        task=next(t for t in dashboard['tasks'] if t['title']=='Obtain revised 32 GB datasheet')
        assert task['due_date']=='2026-11-01' and task['priority']=='high' and task['status']=='resolved' and task['historical'] and len(task['history'])==2
        for doc in docs:
            raw=client.get(prefix+f'/documents/{doc["id"]}/file')
            assert raw.status_code==200 and raw.content==(ROOT/'samples'/'amendments'/doc['filename']).read_bytes()
            pages=get(prefix+f'/documents/{doc["id"]}/pages')
            for req in get(prefix+f'/documents/{doc["id"]}/requirements'):
                source_pages = pages if req['source_document_id']==doc['id'] else get(prefix+f'/documents/{req["source_document_id"]}/pages')
                assert req['excerpt'] in next(p['text'] for p in source_pages if p['page']==req['page'])
        report['checks']['persistence']={'tender_versions':len(docs),'evidence_documents':len(evidence),'snapshots':len(snapshots),'exact_file_bytes_and_source_quotes':True}
        report['checks']['amendment']={'RAM':'Modified 16 GB to 32 GB; old approval reopened','executed_checks':executed,'SSD':'same approved assessment retained','review_history_preserved':True}
        report['checks']['reviews_tasks']={'approval_rejection_reopening_and_correction_saved':True,'correction_appends_assessment':True,'due_date':task['due_date'],'priority':task['priority'],'status':task['status'],'task_history_events':len(task['history']),'historical_task_preserved':True}
        for kind in ('compliance-matrix','evidence-index'):
            response=client.get(prefix+'/exports/'+kind)
            assert response.status_code==200 and 'no-store' in response.headers['cache-control']
            rows=list(csv.DictReader(io.StringIO(response.text)))
            assert rows
            if kind=='compliance-matrix':
                assert 'Conflict detected' in response.text
            assert (Path.home()/'Downloads'/f'{kind}.csv').read_bytes()==response.content
            (ROOT/f'sidebar-audit-{kind}.csv').write_bytes(response.content)
            report['checks'][kind]={'rows':len(rows),'ui_download_matches_api':True,'cache_control':response.headers['cache-control']}
        before=len(docs); negative={}; headers={'Content-Type':'application/pdf','X-Filename':'rejected.pdf'}
        for name,body,extra,expected in [('wrong_type',b'not PDF',{'Content-Type':'text/plain'},415),('malformed_pdf',b'%PDF-broken',{},422),('oversized_pdf',b'%PDF-'+b'x'*settings.upload_max_bytes,{},413)]:
            response=client.post(prefix+'/documents',headers={**headers,**extra},content=body)
            assert response.status_code==expected,(name,response.status_code)
            negative[name]=response.status_code
        assert len(get(prefix+'/documents'))==before
        response=client.get(f'/workspaces/{uuid4()}/documents/{docs[0]["id"]}/file')
        assert response.status_code==404
        negative['cross_workspace_file']=response.status_code
        response=client.get(prefix+'/dashboard',headers={'Origin':'https://untrusted.invalid'})
        assert response.status_code==403
        negative['untrusted_origin']=response.status_code
        report['checks']['negative_paths']=negative
        timeline=get(prefix+'/timeline?offset=0&limit=30')
        assert timeline['items'] and timeline['total']>0
        report['checks']['timeline']={'events':timeline['total']}
        report['readiness']={'review_complete':dashboard['review_complete'],'counts':dashboard['counts'],'blockers':dashboard['blockers']}
    engine=build_engine(settings.database_url)
    with build_session_factory(engine)() as db:
        counts={model.__name__:db.scalar(select(func.count()).select_from(model).where(model.workspace_id==WID)) for model in (DocumentVersion,Assessment,ReviewDecision,CorrectiveTask,TaskEvent)}
        assert counts['DocumentVersion']==3 and counts['ReviewDecision']>=7 and counts['Assessment']>=4
        report['independent_database_counts']=counts
    engine.dispose()
    report['result']='UI/API/database audit passed; live Nemotron blocked by missing API key.'
    (ROOT/'sidebar-audit-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()

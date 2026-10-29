"""Real PDF, extraction, DB transactions, deterministic diff, and review propagation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from tenderready.api import create_app
from tenderready.models import Assessment, AssessmentDependency, ReviewDecision, ReassessmentImpact
from test_documents import config, workspace
from test_verification import pdf, send_pdf, evaluate

RAM16='Requirement ID: RAM-01\nModel: Atlas A14\nRAM: at least 16 GB'
RAM32=RAM16.replace('16 GB','32 GB')
STORAGE='Requirement ID: SSD-01\nModel: Atlas A14\nStorage: at least 512 GB'
AUTH={'reviewer':'Synthetic reviewer','coverage_confirmed':True}


def upload_revision(client,wid,body,kind='amendment'):
    r=client.post(f'/workspaces/{wid}/documents?kind={kind}',content=pdf(body),headers={'Content-Type':'application/pdf','X-Filename':'revision.pdf'})
    assert r.status_code==201,r.text
    d=r.json(); base=f'/workspaces/{wid}/documents/{d["id"]}'
    r=client.post(base+'/extract-labelled'); assert r.status_code==200,r.text
    return d,base


def setup(client):
    wid=workspace(client)
    d,base=upload_revision(client,wid,RAM16+'\n\n'+STORAGE,'tender')
    send_pdf(client,wid,pdf('Model: Atlas A14\nRAM: 16 GB\nStorage: 512 GB'),'datasheet')
    reqs=client.get(base+'/requirements').json(); assessments=[]
    for req in reqs:
        a=evaluate(client,wid,req['id']); assert a['status']=='supported',a
        r=client.post(f'/workspaces/{wid}/assessments/{a["id"]}/reviews',json={'action':'approved','reviewer':'Synthetic reviewer','comment':'Confirmed original requirement.'})
        assert r.status_code==201,r.text
        assessments.append(a)
    snapshot=client.post(base+'/baseline',json=AUTH); assert snapshot.status_code==201,snapshot.text
    return wid,d,base,reqs,assessments,snapshot.json()


def apply(client,base,mode='delta',**extra):
    payload={**AUTH,'mode':mode,**extra}
    preview=client.post(base+'/compare',json=payload); assert preview.status_code==200,preview.text
    payload['fingerprint']=preview.json()['fingerprint']
    result=client.post(base+'/apply-amendment',json=payload)
    assert result.status_code==200,result.text
    return preview.json(),result.json(),payload


def test_ram_amendment_reopens_only_affected_approval(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,original,oldbase,reqs,assessments,baseline=setup(client)
        newdoc,newbase=upload_revision(client,wid,RAM32)
        # Upload/extraction must not invalidate unrelated approvals.
        before=client.get(f'/workspaces/{wid}/snapshots').json()[0]
        assert all(not r['assessment']['stale'] and r['assessment']['review_state']=='approved' for r in before['requirements'])
        plan,result,payload=apply(client,newbase)
        changes={c['classification']:c for c in result['changes']}
        assert set(changes)=={'Modified','Unchanged'}
        changed=changes['Modified']; impact=changed['impacts'][0]
        assert impact['old_assessment']['status']=='supported'
        assert impact['old_assessment']['review_state']=='reopened'
        assert impact['old_assessment']['requires_reassessment']
        assert impact['new_assessment']['status']=='conflicting'
        checks=impact['new_assessment']['checks']
        assert [(c['field'],c['outcome']) for c in checks if c.get('execution')=='executed']==[('ram_gb','conflict')]
        assert {c['field'] for c in checks if c.get('execution')=='reused'}=={'model','product_scope'}
        assert impact['approval_ids']
        assert changed['before']['page']==1 and changed['after']['page']==1
        assert changed['before']['stable_id']==changed['after']['stable_id'] and changed['after']['version']==2
        newram=next(r for r in result['requirements'] if r['clause_id']=='ram-01')
        oldram=next(r for r in baseline['requirements'] if r['clause_id']=='ram-01')
        assert newram['stable_id']==oldram['stable_id'] and newram['version']==2
        unchanged=next(r for r in result['requirements'] if r['clause_id']=='ssd-01')
        originalssd=next(r for r in baseline['requirements'] if r['clause_id']=='ssd-01')
        assert unchanged['assessment']['id']==originalssd['assessment']['id']
        assert unchanged['assessment']['review_state']=='approved' and not unchanged['assessment']['stale']
        assert changes['Unchanged']['impacts']==[]
        # Idempotent application creates no duplicate assessments/reopenings.
        repeated=client.post(newbase+'/apply-amendment',json=payload)
        assert repeated.status_code==200 and repeated.json()['id']==result['id']
        assert client.post(oldbase+'/manual-requirements',json={'page':1,'excerpt':RAM16,'reviewer':'x'}).status_code==409
        assert client.post(oldbase+'/analyze').status_code==409
        rows=client.get(newbase+'/requirements').json()
        assert len(rows)==2 and {r['id'] for r in rows}=={r['requirement_id'] for r in result['requirements']}
        assert client.get(f'/workspaces/{wid}/documents/{original["id"]}/file').content.startswith(b'%PDF-')
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Assessment))==3
        assert db.scalar(select(func.count()).select_from(ReassessmentImpact))==1
        assert db.scalar(select(func.count()).select_from(ReviewDecision).where(ReviewDecision.action=='reopened'))==1
        assert db.scalar(select(func.count()).select_from(AssessmentDependency))>=6
        with pytest.raises(IntegrityError): db.execute(text("UPDATE requirement_changes SET classification='Unchanged'")); db.commit()


def test_full_replacement_removal_and_added_requirement(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,_=setup(client)
        new,base=upload_revision(client,wid,RAM32+'\n\nRequirement ID: NEW-01\nModel: Atlas A14\nRAM: at least 64 GB','tender')
        plan,result,_=apply(client,base,'full')
        assert {c['classification'] for c in result['changes']}=={'Modified','Removed','Added'}
        removed=next(c for c in result['changes'] if c['classification']=='Removed')
        assert removed['after']['page'] is None
        assert removed['impacts'][0]['old_assessment']['review_state']=='reopened'
        assert len(result['requirements'])==2


def test_normalized_unchanged_preserves_approvals(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,baseline=setup(client)
        _,base=upload_revision(client,wid,RAM16.replace('16 GB','16.0 GB')+'\n\n'+STORAGE,'tender')
        _,result,_=apply(client,base,'full')
        assert all(c['classification']=='Unchanged' and c['impacts']==[] for c in result['changes'])
        assert {r['assessment']['id'] for r in result['requirements']}=={r['assessment']['id'] for r in baseline['requirements']}
        assert all(r['assessment']['review_state']=='approved' and not r['assessment']['stale'] for r in result['requirements'])


def test_stale_preview_and_cross_workspace_rejected(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,_=setup(client); other=workspace(client)
        doc,base=upload_revision(client,wid,RAM32)
        preview=client.post(base+'/compare',json=AUTH).json()
        send_pdf(client,wid,pdf('Model: Atlas A14\nRAM: 32 GB'),'datasheet')
        assert client.post(base+'/apply-amendment',json={**AUTH,'fingerprint':preview['fingerprint']}).status_code==409
        assert client.post(f'/workspaces/{other}/documents/{doc["id"]}/compare',json=AUTH).status_code==404
        newplan=client.post(base+'/compare',json=AUTH).json()
        assert client.post(base+'/apply-amendment',json={**AUTH,'coverage_confirmed':False,'fingerprint':newplan['fingerprint']}).status_code==422
        assert len(client.get(f'/workspaces/{wid}/snapshots').json())==1


def test_duplicate_clause_ids_and_uncertain_parsing_fail_closed(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid=workspace(client)
        for textvalue in (RAM16+'\n\n'+RAM32, RAM16+'\nExcept when another model is allowed.'):
            doc=send_pdf(client,wid,pdf(textvalue)); base=f'/workspaces/{wid}/documents/{doc["id"]}'
            assert client.post(base+'/extract-labelled').status_code==422
            assert client.get(base+'/requirements').json()==[]


def test_explicit_delta_removal_requires_exact_source(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,snap=setup(client)
        ssd=next(r for r in snap['requirements'] if r['clause_id']=='ssd-01')
        doc=send_pdf(client,wid,pdf('Remove requirement SSD-01.'))
        base=f'/workspaces/{wid}/documents/{doc["id"]}'
        removal={'requirement_id':ssd['requirement_id'],'page':1,'quote':'Invented deletion'}
        assert client.post(base+'/compare',json={**AUTH,'removals':[removal]}).status_code==422
        removal['quote']='Remove requirement SSD-01.'
        _,result,_=apply(client,base,removals=[removal])
        assert {c['classification'] for c in result['changes']}=={'Removed','Unchanged'}
        assert result['requirements'][0]['clause_id']=='ram-01'


def test_second_amendment_uses_active_snapshot_and_preserves_lineage(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,_=setup(client)
        _,base=upload_revision(client,wid,RAM32); _,first,_=apply(client,base)
        _,base2=upload_revision(client,wid,RAM32.replace('32 GB','64 GB')); _,second,_=apply(client,base2)
        ram=next(r for r in second['requirements'] if r['clause_id']=='ram-01')
        assert ram['version']==3 and ram['assessment']['status']=='conflicting'
        assert second['previous_snapshot_id']==first['id']
        assert next(r for r in second['requirements'] if r['clause_id']=='ssd-01')['assessment']['review_state']=='approved'


def test_failed_reassessment_rolls_back_every_change(database,tmp_path,monkeypatch):
    from tenderready import amendments
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1),raise_server_exceptions=False) as client:
        wid,_,_,_,_,_=setup(client); _,base=upload_revision(client,wid,RAM32)
        plan=client.post(base+'/compare',json=AUTH).json()
        def fail(*args,**kwargs): raise RuntimeError('Simulated transactional failure')
        monkeypatch.setattr(amendments,'verify',fail)
        result=client.post(base+'/apply-amendment',json={**AUTH,'fingerprint':plan['fingerprint']})
        assert result.status_code==500
        history=client.get(f'/workspaces/{wid}/snapshots').json()
        assert len(history)==1
        assert all(r['assessment']['review_state']=='approved' for r in history[0]['requirements'])
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ReassessmentImpact))==0
            assert db.scalar(select(func.count()).select_from(Assessment))==2


def test_nemotron_interpretation_path_and_uncertain_propagation(database,tmp_path):
    from test_documents import provider_factory
    engine,_=database; app=create_app(config(tmp_path),engine)
    calls=[]; app.state.nemotron_factory=provider_factory('success',calls)
    with TestClient(base_url="http://127.0.0.1:8000", app=app,client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,snapshot=setup(client)
        textvalue='The supplier must provide at least 32 GB of RAM with an equivalent model allowed.'
        doc=client.post(f'/workspaces/{wid}/documents?kind=amendment',content=pdf(textvalue),headers={'Content-Type':'application/pdf','X-Filename':'prose-amendment.pdf'}).json()
        base=f'/workspaces/{wid}/documents/{doc["id"]}'
        assert client.post(base+'/analyze').status_code==202
        reqs=client.get(base+'/requirements').json()
        assert len(reqs)==1 and reqs[0]['provenance']=='nemotron_extraction' and calls
        oldram=next(r for r in snapshot['requirements'] if r['clause_id']=='ram-01')
        _,result,_=apply(client,base,mappings=[{'candidate_id':reqs[0]['id'],'previous_requirement_id':oldram['requirement_id']}])
        change=next(c for c in result['changes'] if c['classification']=='Modified')
        assert change['impacts'][0]['new_assessment']['status']=='inconclusive'
        assert change['impacts'][0]['old_assessment']['review_state']=='reopened'
        assert next(r for r in result['requirements'] if r['clause_id']=='ssd-01')['assessment']['review_state']=='approved'


def test_ambiguous_exact_matches_require_explicit_mapping(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid=workspace(client); textvalue='Model: Atlas A14\nRAM: at least 16 GB'
        doc=send_pdf(client,wid,pdf(textvalue));base=f'/workspaces/{wid}/documents/{doc["id"]}'
        for _ in range(2):
            assert client.post(base+'/manual-requirements',json={'page':1,'excerpt':textvalue,'reviewer':'test'}).status_code==201
        assert client.post(base+'/baseline',json=AUTH).status_code==201
        newdoc=send_pdf(client,wid,pdf(textvalue));newbase=f'/workspaces/{wid}/documents/{newdoc["id"]}'
        client.post(newbase+'/manual-requirements',json={'page':1,'excerpt':textvalue,'reviewer':'test'})
        assert client.post(newbase+'/compare',json=AUTH).status_code==422


def test_dependency_cannot_link_an_unrelated_requirement(database,tmp_path):
    engine,sessions=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,reqs,assessments,_=setup(client)
        with sessions() as db:
            db.add(AssessmentDependency(workspace_id=wid,assessment_id=assessments[0]['id'],requirement_version_id=reqs[1]['id'],field='ram_gb'))
            with pytest.raises(IntegrityError): db.commit()


def test_checked_in_sample_pdfs_extract_without_invented_pages(database,tmp_path):
    from pathlib import Path
    engine,_=database
    root=Path(__file__).parents[2]/'samples'/'amendments'
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid=workspace(client)
        for filename,expected in [('original-tender.pdf',2),('ram-corrigendum.pdf',1)]:
            doc=send_pdf(client,wid,(root/filename).read_bytes())
            base=f'/workspaces/{wid}/documents/{doc["id"]}'
            response=client.post(base+'/extract-labelled')
            assert response.status_code==200,response.text
            rows=client.get(base+'/requirements').json()
            assert len(rows)==expected and all(r['page']==1 for r in rows)
            assert all('End requirement' not in r['text'] for r in rows)


def test_renumbered_clause_keeps_identity_on_following_amendment(database,tmp_path):
    engine,_=database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path),engine),client=('127.0.0.1',1)) as client:
        wid,_,_,_,_,snap=setup(client)
        oldram=next(r for r in snap['requirements'] if r['clause_id']=='ram-01')
        _,base=upload_revision(client,wid,RAM16.replace('RAM-01','RAM-RENUMBERED'))
        candidate=client.get(base+'/requirements').json()[0]
        _,renumbered,_=apply(client,base,mappings=[{'candidate_id':candidate['id'],'previous_requirement_id':oldram['requirement_id']}])
        assert all(c['classification']=='Unchanged' for c in renumbered['changes'])
        _,nextbase=upload_revision(client,wid,RAM32.replace('RAM-01','RAM-RENUMBERED'))
        _,updated,_=apply(client,nextbase)
        current=next(r for r in updated['requirements'] if r['clause_id']=='ram-renumbered')
        assert current['stable_id']==oldram['stable_id'] and current['version']==2
        assert next(c for c in updated['changes'] if c['classification']=='Modified')['match_method']=='explicit_clause_id'

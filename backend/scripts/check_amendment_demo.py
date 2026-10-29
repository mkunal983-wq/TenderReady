"""Read-only confirmation of the UI-created amendment scenario, HTTP plus SQL."""
import json
from pathlib import Path
import httpx
from sqlalchemy import select
from tenderready.config import Settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import Assessment, ReviewDecision, AssessmentDependency, ReassessmentImpact


def main():
    settings=Settings();token=settings.app_api_token.get_secret_value()
    with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':f'Bearer {token}'} if token else {}) as client:
        response=client.get('/workspaces');response.raise_for_status()
        workspace=next(w for w in response.json() if w['title']=='Amendment UI demo — RAM 16 to 32 GB')
        prefix='/workspaces/'+workspace['id']; response=client.get(prefix+'/snapshots');response.raise_for_status()
        history=response.json();assert len(history)==2
        current,original=history
        ram=next(r for r in current['requirements'] if r['clause_id']=='ram-01')
        ssd=next(r for r in current['requirements'] if r['clause_id']=='ssd-01')
        oldram=next(r for r in original['requirements'] if r['clause_id']=='ram-01')
        oldssd=next(r for r in original['requirements'] if r['clause_id']=='ssd-01')
        assert ram['stable_id']==oldram['stable_id'] and ram['version']==2
        change=next(c for c in current['changes'] if c['classification']=='Modified')
        assert change['before']['stable_id']==change['after']['stable_id']==ram['stable_id']
        assert change['after']['version']==2
        assert ram['assessment']['status']=='conflicting'
        assert oldram['assessment']['status']=='supported' and oldram['assessment']['review_state']=='reopened'
        assert ssd['assessment']['id']==oldssd['assessment']['id'] and ssd['assessment']['review_state']=='approved'
        assert not ssd['assessment']['stale']
        checks=ram['assessment']['checks']
        executed=[c['field'] for c in checks if c.get('execution')=='executed']
        reused=[c['field'] for c in checks if c.get('execution')=='reused']
        assert executed==['ram_gb'] and set(reused)=={'model','product_scope'}
        documents=client.get(prefix+'/documents').json();assert len(documents)==2
        for d in documents: assert client.get(prefix+f'/documents/{d["id"]}/file').content.startswith(b'%PDF-')
    engine=build_engine(settings.database_url)
    with build_session_factory(engine)() as db:
        assessments=list(db.scalars(select(Assessment).where(Assessment.workspace_id==workspace['id'])))
        reviews=list(db.scalars(select(ReviewDecision).where(ReviewDecision.workspace_id==workspace['id'])))
        impacts=list(db.scalars(select(ReassessmentImpact).where(ReassessmentImpact.workspace_id==workspace['id'])))
        dependencies=list(db.scalars(select(AssessmentDependency).where(AssessmentDependency.workspace_id==workspace['id'])))
        assert len(assessments)==3 and len(reviews)>=3 and len(impacts)==1
        assert len(dependencies)==9
    report={'result':'passed','workflow':'Created, uploaded, extracted, verified, approved, compared, and applied through the existing UI',
        'workspace_id':workspace['id'],'snapshot_count':len(history),'ram_stable_id':ram['stable_id'],
        'old_ram_assessment_id':oldram['assessment']['id'],'new_ram_assessment_id':ram['assessment']['id'],
        'ram_change':'Modified: 16 GB -> 32 GB','old_ram_status':oldram['assessment']['status'],
        'old_ram_review':oldram['assessment']['review_state'],'new_ram_status':ram['assessment']['status'],
        'executed_fields':executed,'reused_fields':reused,'unrelated_storage_assessment_id':ssd['assessment']['id'],
        'unrelated_storage_review':ssd['assessment']['review_state'],'unrelated_storage_stale':ssd['assessment']['stale'],
        'assessment_count':len(assessments),'review_count':len(reviews),'impact_count':len(impacts),'dependency_count':len(dependencies),
        'requirement_extraction':'deterministic labelled grammar; no provider was mocked in the UI demo',
        'live_nemotron':'not_run_key_pending','official_verification':False}
    path=Path(__file__).resolve().parents[2]/'amendment-demo-report.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

from test_batch_verification import client_for, store_requirements
from test_documents import workspace
from test_verification import send_pdf, pdf
from tenderready.models import Assessment


def test_combined_dependency_review_change_stales_parent_preserves_history(database,tmp_path):
 engine,sessions=database
 with client_for(engine,tmp_path) as c:
  wid=workspace(c);base=f'/workspaces/{wid}'
  a='Model: Atlas A14\nRAM: at least 32 GB'
  b='Model: Atlas A14\nStorage: at least 512 GB'
  _,ids=store_requirements(c,sessions,wid,[(a,{}),(b,{}),(a+'\n'+b,{}),('Model: Atlas A14\nRAM: at least 64 GB',{})])
  send_pdf(c,wid,pdf('Model: Atlas A14\nRAM: 32 GB\nStorage: 512 GB'),'datasheet')
  first=c.post(base+'/verify-all',json={}).json()
  assert first.get('failed')==0, first
  def view(rid):return c.get(base+f'/requirements/{rid}/verification').json()['assessments'][0]
  parent=view(ids[2]);child=view(ids[0])
  deps=[x for x in parent['checks'] if x.get('method')=='component_dependency']
  assert len(deps)==2 and all(x['outcome']=='pass' for x in deps)
  assert parent['status']=='supported' and not parent['stale']
  with sessions() as db:
   stored=db.get(Assessment,parent['id'])
   assert {x['requirement_id'] for x in stored.checks if x.get('method')=='component_dependency'}==set(ids[:2])
  assert c.post(base+'/verify-all',json={}).json()['checked']==0
  unrelated=view(ids[3])
  assert c.post(base+f'/assessments/{unrelated["id"]}/reviews',json={'action':'rejected','reviewer':'QA','comment':'Unrelated finding'}).status_code==201
  assert not view(ids[2])['stale']
  result=c.post(base+f'/assessments/{child["id"]}/reviews',json={'action':'rejected','reviewer':'QA','comment':'Need corrected component evidence'})
  assert result.status_code==201
  assert view(ids[2])['stale']
  approval=c.post(base+f'/assessments/{parent["id"]}/reviews',json={'action':'approved','reviewer':'QA','comment':'Cannot approve a stale parent'})
  assert approval.status_code==409
  rerun=c.post(base+f'/requirements/{ids[2]}/verify',json={})
  assert rerun.status_code==201 and rerun.json()['status']=='inconclusive'
  assert rerun.json()['id']!=parent['id']
  with sessions() as db: assert db.get(Assessment,parent['id']).checks==parent['checks']


def test_dependencies_do_not_cross_workspace_or_source_document(database,tmp_path):
 engine,sessions=database
 with client_for(engine,tmp_path) as c:
  wid=workspace(c);other=workspace(c)
  text='Model: Atlas A14\nRAM: at least 32 GB'
  store_requirements(c,sessions,other,[(text,{})])
  store_requirements(c,sessions,wid,[(text,{})])
  _,ids=store_requirements(c,sessions,wid,[(text+'\nStorage: at least 512 GB',{})])
  plan=c.get(f'/workspaces/{wid}/requirements/{ids[0]}/verification').json()['check_plan']
  assert plan['dependencies']==[]

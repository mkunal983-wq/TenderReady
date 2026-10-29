from fastapi.testclient import TestClient
from tenderready.api import create_app
from test_documents import config, workspace
from test_verification import transcribe


def test_procedures_become_tasks_without_completion_or_duplicates(database,tmp_path):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  transcribe(c,wid,'The bidder shall submit the signed application online.')
  base=f'/workspaces/{wid}'
  assert c.post(base+'/verify-all',json={}).status_code==200
  first=c.get(base+'/dashboard').json()
  actions=[t for t in first['tasks'] if t['title'].startswith('Tender action:')]
  assert first['requirements'][0]['status']=='action_required'
  assert first['requirements'][0]['unresolved']
  assert len(actions)==1 and actions[0]['status']=='open' and actions[0]['due_date'] is None
  assert '#page=2' in actions[0]['explanation'] and not first['review_complete']
  c.post(base+'/verify-all',json={})
  assert c.get(base+'/dashboard').json()['tasks']==first['tasks']


def test_exact_reference_metadata_does_not_claim_evidence_support(database,tmp_path):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  transcribe(c,wid,'Published Date 01.09.2015 (2000 hrs)')
  b=f'/workspaces/{wid}'
  c.post(b+'/verify-all',json={})
  d=c.get(b+'/dashboard').json();row=d['requirements'][0]
  assert row['status']=='reference_only' and not row['blocking'] and not row['unresolved']
  assert row['assessment']['review_state']=='awaiting_review'
  assert not d['review_complete']  # A reviewed baseline is still required.


def test_routed_actions_preserve_history_and_do_not_approve(database,tmp_path):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  req,_=transcribe(c,wid,'Bidders are required to enroll on the Central Public Procurement Portal.')
  base=f'/workspaces/{wid}'
  c.post(base+'/verify-all',json={})
  first=c.get(base+'/dashboard').json()
  assert first['requirements'][0]['status']=='action_required'
  task=next(t for t in first['tasks'] if t['title'].startswith('Tender action:'))
  assert 'never upload passwords' in task['explanation']
  assert task['status']=='open' and task['due_date'] is None
  assert not first['review_complete']
  history=c.get(base+f'/requirements/{req["id"]}/verification').json()['assessments']
  c.post(base+'/verify-all',json={})
  assert c.get(base+'/dashboard').json()['tasks']==first['tasks']
  assert c.get(base+f'/requirements/{req["id"]}/verification').json()['assessments']==history


def test_actions_do_not_hide_uncertainty_or_match_hardware():
 from tenderready.clause_actions import action_for,interpretation_uncertain
 assert action_for('The Ministry reserves the right to reject any bid.')['rule']=='contract_terms'
 assert action_for('Processor: 5th Generation Intel Core i5 or above') is None
 assert action_for('Bidder must submit a laptop with 32 GB RAM') is None
 for flag in ['ambiguous','quantity_conflict','unresolved_interpretations']:
  assert interpretation_uncertain({flag:True})
 assert interpretation_uncertain({'confidence':'medium'})
 assert interpretation_uncertain({'review_reasons':['Model reports uncertainty; verify against the source.']})


def test_boq_quantity_becomes_source_linked_task_not_hardware_limit(database,tmp_path):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  transcribe(c,wid,'3.00 Tablets 2.0000   0.0000 0.0000 INR Zero Only')
  base=f'/workspaces/{wid}'
  c.post(base+'/verify-all',json={})
  d=c.get(base+'/dashboard').json()
  assert d['requirements'][0]['status']=='action_required'
  task=next(t for t in d['tasks'] if t['title'].startswith('Tender action:'))
  assert 'schedule quantity 2.0000' in task['explanation']
  assert 'not a minimum hardware specification' in task['explanation']
  assert not d['review_complete'] and task['due_date'] is None


def test_literal_advice_becomes_action_without_erasing_extraction_review(database,tmp_path):
 from test_batch_verification import store_requirements
 from tenderready.models import RequirementVersion
 engine,sessions=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  statement='4.8 Prospective bidders are accordingly advised to go through instructions provided at Central Public Procurement Portal;'
  original={'excerpt':statement,'confidence':'medium','requires_human_review':True,
    'review_reasons':['Model reports uncertainty; verify against the source.']}
  _,ids=store_requirements(c,sessions,wid,[(statement,original)])
  req={'id':ids[0]}
  base=f'/workspaces/{wid}'
  c.post(base+'/verify-all',json={})
  d=c.get(base+'/dashboard').json();r=d['requirements'][0]
  assert r['status']=='action_required' and r['blocking'] and r['unresolved']
  assert not d['review_complete'] and r['assessment']['review_state']=='awaiting_review'
  with sessions() as db: assert db.get(RequirementVersion,req['id']).condition==original
  task=next(t for t in d['tasks'] if t['title'].startswith('Tender action:'))
  assert 'no mandatory obligation is inferred' in task['explanation']


def test_literal_action_requires_whole_clause_and_original_source():
 from tenderready.clause_actions import literal_action
 from tenderready.check_planning import build_check_plan
 from test_check_planning import inputs
 text='1. Financial bid as per Annexure II of this tender document .xls'
 assert literal_action(text)
 assert not literal_action(text+' unless the buyer waives this requirement')
 assert not literal_action(text.replace('.xls','.pdf'))
 req,span=inputs(text);span.text='unrelated'
 plan=build_check_plan(req,span)
 assert plan['kind']!='procedure' and plan['unhandled']

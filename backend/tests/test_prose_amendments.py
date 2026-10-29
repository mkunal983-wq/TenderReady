"""Real PDF/API/DB tests; provider transport is a test-only fixture, not live AI."""
import json
import re
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from tenderready.api import create_app
from tenderready.config import Settings
from tenderready.nebius import NemotronClient
from tenderready.verification import threshold_sentence
from tenderready.amendments import transfer_spec
from test_documents import config, workspace
from test_verification import pdf, send_pdf

RAM = 'The Atlas A14 product must have at least 16 GB RAM.'
SSD = 'The Atlas A14 product must have at least 512 GB storage.'
AUTH = {'reviewer': 'Synthetic test reviewer', 'coverage_confirmed': True}


def interpreted(statement=RAM, **overrides):
    number = re.search(r'(\d+) GB', statement)[1]
    condition = {'confidence': 'high', 'numeric_conditions': [{'operator': '>=', 'value_text': number,
                 'unit_text': 'GB', 'quote': statement}], 'date_conditions': [], 'review_reasons': []}
    condition.update(overrides)
    return SimpleNamespace(statement=statement, obligation='mandatory', category='numeric_threshold', condition=condition)


def provider(settings):
    settings = settings.model_copy(update={'nebius_api_key': Settings(_env_file=None, nebius_api_key='test-only').nebius_api_key})
    def respond(request):
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'object':'list','data':[{'id':settings.nebius_model,'created':1,'object':'model','owned_by':'nvidia'}]})
        source = json.loads(json.loads(request.content)['messages'][1]['content'])['sources'][0]
        requirements = []
        for sentence in source['text'].splitlines():
            if 'must have' not in sentence:
                continue
            req = interpreted(sentence)
            requirements.append({'statement':sentence,'category':'product_identity' if '32 GB' in sentence else 'numeric_threshold',
                'obligation':'mandatory','obligation_quote':'must',
                'citations':[{'source_id':source['source_id'],'quote':sentence}], **req.condition})
        return httpx.Response(200,json={'id':'test-only','created':1,'object':'chat.completion','model':settings.nebius_model,
            'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps({'requirements':requirements,'warnings':[]})},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}})
    return NemotronClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(respond)))


def extract(client, wid, text):
    doc = send_pdf(client, wid, pdf(text))
    base = f'/workspaces/{wid}/documents/{doc["id"]}'
    assert client.post(base+'/analyze').status_code == 202
    rows = client.get(base+'/requirements').json()
    assert rows and all(r['provenance']=='nemotron_extraction' for r in rows)
    return base, rows


def baseline(client, wid, text=RAM+'\n'+SSD):
    base, rows = extract(client, wid, text)
    send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 16 GB\nStorage: 512 GB'), 'datasheet')
    for row in rows:
        a = client.post(f'/workspaces/{wid}/requirements/{row["id"]}/verify',json=AUTH).json()
        assert a['status']=='supported', a
        assert client.post(f'/workspaces/{wid}/assessments/{a["id"]}/reviews',json={
            'reviewer':AUTH['reviewer'],'action':'approved','comment':'Inspected synthetic sources.'}).status_code==201
    result=client.post(base+'/baseline',json=AUTH)
    assert result.status_code==201, result.text
    return result.json()


def test_prose_auto_mapping_selective_reassessment_and_history(database,tmp_path):
    engine,_=database
    app=create_app(config(tmp_path),engine); app.state.nemotron_factory=provider
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as client:
        wid=workspace(client); original=baseline(client,wid)
        base,_=extract(client,wid,RAM.replace('16 GB','32 GB'))
        payload={**AUTH,'mode':'delta'}  # No mapping or replacement criteria.
        plan=client.post(base+'/compare',json=payload).json()
        modified=next(c for c in plan['changes'] if c['classification']=='Modified')
        assert modified['match_method']=='source_grounded_threshold'
        assert modified['before']['page']==modified['after']['page']==1
        result=client.post(base+'/apply-amendment',json={**payload,'fingerprint':plan['fingerprint']})
        assert result.status_code==200,result.text
        current=result.json(); change=next(c for c in current['changes'] if c['classification']=='Modified')
        impact=change['impacts'][0]
        assert impact['old_assessment']['review_state']=='reopened'
        assert [r['action'] for r in impact['old_assessment']['reviews']]==['approved','reopened']
        assert impact['approval_ids']==[impact['old_assessment']['reviews'][0]['id']]
        new=impact['new_assessment']; assert new['status']=='conflicting' and new['review_state']=='awaiting_review'
        assert {(c['field'],c['outcome']) for c in new['checks'] if c.get('execution')=='executed'}=={('coverage','pass'),('ram_gb','conflict')}
        assert {c['field'] for c in new['checks'] if c.get('execution')=='reused'}=={'model','product_scope'}
        for reused in (c for c in new['checks'] if c.get('execution')=='reused'):
            prior = next(c for c in impact['old_assessment']['checks'] if c.get('field')==reused['field'])
            assert {k: v for k, v in reused.items() if k not in {'execution', 'reused_from_assessment_id'}} == {
                k: v for k, v in prior.items() if k != 'execution'}
        ram=next(c for c in new['checks'] if c.get('field')=='ram_gb')
        assert '32' in ram['rationale'] and '16 GB' in ram['rationale'] and ram['sources'][0]['page']==1
        assert change['before']['stable_id']==change['after']['stable_id'] and change['after']['version']==2
        oldssd=next(r for r in original['requirements'] if 'storage' in r['text'])
        newssd=next(r for r in current['requirements'] if 'storage' in r['text'])
        assert oldssd['assessment']['id']==newssd['assessment']['id']
        assert newssd['assessment']['review_state']=='approved' and not newssd['assessment']['stale']
        repeated=client.post(base+'/apply-amendment',json={**payload,'fingerprint':plan['fingerprint']}).json()
        assert repeated['id']==current['id']


@pytest.mark.parametrize('original,new',[(RAM+'\n'+RAM.replace('16','8'),RAM.replace('16','32')),(RAM,RAM.replace('16','32')+'\n'+RAM.replace('16','64'))])
def test_duplicate_prose_requires_mapping_without_mutations(database,tmp_path,original,new):
    engine,_=database; app=create_app(config(tmp_path),engine); app.state.nemotron_factory=provider
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as client:
        wid=workspace(client); baseline(client,wid,original)
        base,_=extract(client,wid,new)
        result=client.post(base+'/compare',json=AUTH)
        assert result.status_code==422 and 'Ambiguous' in result.text
        snapshots=client.get(f'/workspaces/{wid}/snapshots').json()
        assert len(snapshots)==1 and all(r['assessment']['review_state']=='approved' for r in snapshots[0]['requirements'])


@pytest.mark.parametrize('sentence',[
 RAM.replace('must have','must not have'), RAM[:-1]+' unless unavailable.',
 RAM[:-1]+' or equivalent.', RAM[:-1]+' and 512 GB storage.',
 RAM.replace('GB','TB'), RAM.replace('at least','more than'),
 RAM.replace('must','may'), RAM.replace('Atlas A14','Atlas A14 or B20'),
])
def test_uncertain_or_unsupported_prose_has_no_auto_identity(sentence):
    req=interpreted(); req.statement=sentence
    assert threshold_sentence(req) is None


@pytest.mark.parametrize('overrides',[
 {'confidence':'medium'}, {'review_reasons':['Ambiguous model scope']},
 {'ambiguous':True}, {'requires_human_review':True},
 {'numeric_conditions':[]}, {'date_conditions':[{'relation':'before'}]},
 {'numeric_conditions':[{'operator':'<=','value_text':'16','unit_text':'GB','quote':RAM}]},
 {'numeric_conditions':[{'operator':'>=','value_text':'32','unit_text':'GB','quote':RAM}]},
])
def test_model_uncertainty_or_disagreement_cannot_enable_transfer(overrides):
    assert threshold_sentence(interpreted(**overrides)) is None


def test_explicit_manual_review_category_is_not_bypassed():
    req=interpreted(); req.category='manual_review'
    assert threshold_sentence(req) is None


def test_transfer_rejects_scope_or_reviewer_interpretation_changes():
    old=interpreted(); new=interpreted(RAM.replace('16','32'))
    criteria=threshold_sentence(old)['criteria']
    prior=SimpleNamespace(checks=[{'method':'verification_context','coverage_confirmed':True,'criteria':criteria}])
    assert transfer_spec(old,new,prior)[1]=={'ram_gb'}
    assert transfer_spec(old,interpreted(RAM.replace('Atlas A14','Atlas B20')),prior)==(None,None)
    prior.checks[0]['criteria']=[{**c,'operator':'lte'} if c['field']=='ram_gb' else c for c in criteria]
    assert transfer_spec(old,new,prior)==(None,None)


def test_uncertain_mapped_change_reopens_but_does_not_inherit_coverage(database,tmp_path):
    engine,_=database; app=create_app(config(tmp_path),engine); app.state.nemotron_factory=provider
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as client:
        wid=workspace(client); original=baseline(client,wid)
        base,rows=extract(client,wid,RAM.replace('16','32')[:-1]+' unless an equivalent model is offered.')
        old=next(r for r in original['requirements'] if 'RAM' in r['text'])
        payload={**AUTH,'mappings':[{'candidate_id':rows[0]['id'],'previous_requirement_id':old['requirement_id']}]}
        plan=client.post(base+'/compare',json=payload).json()
        current=client.post(base+'/apply-amendment',json={**payload,'fingerprint':plan['fingerprint']}).json()
        impact=next(c for c in current['changes'] if c['classification']=='Modified')['impacts'][0]
        assert impact['old_assessment']['review_state']=='reopened'
        new=impact['new_assessment']
        assert new['status']=='inconclusive' and new['review_state']=='awaiting_review'
        assert not new['checks'][0]['coverage_confirmed']
        assert not any(c.get('execution')=='reused' for c in new['checks'])


def test_changed_evidence_is_rechecked_instead_of_reusing_model_result(database,tmp_path):
    engine,_=database; app=create_app(config(tmp_path),engine); app.state.nemotron_factory=provider
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as client:
        wid=workspace(client); baseline(client,wid)
        base,_=extract(client,wid,RAM.replace('16','32'))
        send_pdf(client,wid,pdf('Model: Atlas B20\nRAM: 32 GB'),'datasheet')
        plan=client.post(base+'/compare',json=AUTH).json()
        result=client.post(base+'/apply-amendment',json={**AUTH,'fingerprint':plan['fingerprint']}).json()
        new=next(c for c in result['changes'] if c['classification']=='Modified')['impacts'][0]['new_assessment']
        assert new['status']=='conflicting'
        assert not any(c.get('execution')=='reused' for c in new['checks'])
        assert any(c.get('field')=='model' and c['outcome']=='conflict' for c in new['checks'])

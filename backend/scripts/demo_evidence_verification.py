"""Real HTTP + real PDF/storage/DB demo. Human transcription; no AI is simulated."""
import json
from pathlib import Path
import httpx
from tenderready.config import Settings
from create_verification_samples import OUTPUT, PRODUCT, VALIDITY, PROJECT


def main():
    settings=Settings()
    token=settings.app_api_token.get_secret_value()
    headers={'Authorization':f'Bearer {token}'} if token else {}
    report={'transport':'real HTTP localhost:8000','requirement_source':'explicit human transcription of exact PDF excerpts',
            'provider_calls':0,'official_verification':False,'scenarios':[]}
    with httpx.Client(base_url='http://127.0.0.1:8000',headers=headers,timeout=60) as client:
        def call(method,path,**kwargs):
            response=client.request(method,path,**kwargs); response.raise_for_status(); return response.json()
        for name,file,kind,statement,expected in [
            ('Wrong laptop model','wrong-model.pdf','datasheet',PRODUCT,'conflicting'),
            ('Insufficient RAM','insufficient-ram.pdf','datasheet',PRODUCT,'conflicting'),
            ('Matching labelled fields','matching-datasheet.pdf','datasheet',PRODUCT,'supported'),
            ('Expired certificate','expired-certificate.pdf','certificate',VALIDITY,'outdated'),
            ('Wrong bidder','wrong-bidder.pdf','certificate',VALIDITY,'conflicting'),
            ('Insufficient project value','small-project.pdf','project_reference',PROJECT,'conflicting'),
            ('Missing evidence',None,'datasheet',PRODUCT,'missing'),
        ]:
            workspace=call('POST','/workspaces',json={'title':'Evidence demo: '+name,'supplier_name':'Demo Supplier Pvt Ltd'})
            prefix='/workspaces/'+workspace['id']
            tender=call('POST',prefix+'/documents',content=(OUTPUT/'tender.pdf').read_bytes(),headers={'Content-Type':'application/pdf','X-Filename':'tender.pdf'})
            requirement=call('POST',prefix+f'/documents/{tender["id"]}/manual-requirements',json={'page':1,'excerpt':statement,'reviewer':'Synthetic demo reviewer'})
            if file:
                data=(OUTPUT/file).read_bytes()
                evidence=call('POST',prefix+'/evidence?evidence_type='+kind,content=data,headers={'Content-Type':'application/pdf','X-Filename':file})
                response=client.get(prefix+f'/documents/{evidence["id"]}/file'); response.raise_for_status(); assert response.content==data
            spec=call('GET',prefix+f'/requirements/{requirement["id"]}/verification')['suggested_criteria']
            for c in spec:
                c['evidence_type']=kind
                if c['field']=='valid_until': c['operator']='gte'
            payload={'criteria':spec,'coverage_confirmed':True,'reviewer':'Synthetic demo reviewer'}
            result=call('POST',prefix+f'/requirements/{requirement["id"]}/verify',json=payload)
            assert result['status']==expected,(name,result)
            reviewed=call('POST',prefix+f'/assessments/{result["id"]}/reviews',json={'action':'approved','reviewer':'Synthetic demo reviewer','comment':'Reviewed synthetic fixture; agree with finding, not official verification.'})
            assert reviewed['review_state']=='approved' and reviewed['status']==expected
            repeated=call('POST',prefix+f'/requirements/{requirement["id"]}/verify',json=payload)
            history=call('GET',prefix+f'/requirements/{requirement["id"]}/verification')['assessments']
            assert len(history)==2 and repeated['id']!=result['id']
            item={'scenario':name,'workspace_id':workspace['id'],'requirement_id':requirement['id'],
                  'status':result['status'],'label':result['label'],'assessment_id':result['id'],
                  'history_count':len(history),'review_persisted':history[1]['review_state']=='approved',
                  'source_pages':sorted({s['page'] for c in result['checks'] for s in c.get('sources',[])})}
            report['scenarios'].append(item)
    report['result']='passed'
    target=Path(__file__).resolve().parents[2]/'verification-demo-report.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()

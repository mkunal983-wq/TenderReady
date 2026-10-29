from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

from tenderready.api import create_app
from tenderready.config import Settings
from tenderready.models import Workspace, DocumentVersion


def local(engine, **settings):
    return TestClient(create_app(Settings(_env_file=None, **settings), engine),
                      base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1234))


def test_rename_persists_and_rejects_stale_or_invalid_titles(database):
    engine, sessions = database
    with local(engine) as c:
        w = c.post('/workspaces', json={'title':'Original tender','supplier_name':'Supplier'}).json()
        path = f'/workspaces/{w["id"]}/rename'
        for title in ('', ' ', 'x'*201, 'Bad\ntitle'):
            assert c.post(path, json={'title':title,'expected_title':w['title']}).status_code == 422
        renamed = c.post(path, json={'title':'  Updated tender  ','expected_title':w['title']})
        assert renamed.status_code == 200
        assert renamed.json()['title'] == 'Updated tender'
        assert renamed.json()['revision'] == w['revision']  # Metadata does not invalidate evidence.
        assert c.post(path, json={'title':'Stale edit','expected_title':w['title']}).status_code == 409
        assert c.get('/workspaces').json()[0]['title'] == 'Updated tender'
    with sessions() as db:
        assert db.get(Workspace, w['id']).title == 'Updated tender'


def test_confirmed_delete_hides_workspace_and_blocks_all_scoped_routes_but_retains_files(database, tmp_path):
    engine, sessions = database
    with local(engine, storage_dir=tmp_path/'files') as c:
        w = c.post('/workspaces', json={'title':'Synthetic delete test','supplier_name':'Supplier'}).json()
        other = c.post('/workspaces', json={'title':'Keep this workspace','supplier_name':'Supplier'}).json()
        p = f'/workspaces/{w["id"]}'
        content = BytesIO(); pdf = canvas.Canvas(content); pdf.drawString(40,700,'A real PDF for workspace deletion tests.'); pdf.save()
        uploaded = c.post(p+'/documents', content=content.getvalue(), headers={'Content-Type':'application/pdf','X-Filename':'source.pdf'})
        assert uploaded.status_code == 201
        doc = uploaded.json()
        for payload in ({'expected_title':w['title']}, {'confirm':False,'expected_title':w['title']}, {'confirm':'true','expected_title':w['title']}):
            assert c.post(p+'/delete', json=payload).status_code == 422
        assert c.post(p+'/delete', json={'confirm':True,'expected_title':'wrong title'}).status_code == 409
        assert c.get(p).status_code == 200
        assert c.post(p+'/delete', json={'confirm':True,'expected_title':w['title']}).status_code == 200
        assert [r['id'] for r in c.get('/workspaces').json()] == [other['id']]
        for suffix in ('','/documents','/dashboard','/evidence','/snapshots','/timeline','/exports/compliance-matrix',f'/documents/{doc["id"]}/file'):
            assert c.get(p+suffix).status_code == 404
        assert c.post(p+'/rename', json={'title':'Resurrect','expected_title':w['title']}).status_code == 404
        assert c.post(p+'/documents', content=content.getvalue(), headers={'Content-Type':'application/pdf','X-Filename':'source.pdf'}).status_code == 404
        assert c.get(f'/workspaces/{other["id"]}').status_code == 200
    with sessions() as db:
        assert db.get(Workspace,w['id']).deleted_at is not None
        saved = db.scalar(select(DocumentVersion).where(DocumentVersion.id==doc['id']))
        assert saved and (tmp_path/'files'/saved.storage_key).read_bytes() == content.getvalue()


def test_management_endpoints_require_authorization_and_validate_ids(database):
    engine, _ = database
    with local(engine, app_env='production',app_api_token='x'*32) as c:
        for action in ('rename','delete'):
            assert c.post(f'/workspaces/{uuid4()}/{action}',json={}).status_code == 401
    with local(engine) as c:
        for action,payload in [('rename',{'title':'New','expected_title':'Old'}),('delete',{'confirm':True,'expected_title':'Old'})]:
            assert c.post(f'/workspaces/{uuid4()}/{action}',json=payload).status_code == 404
            assert c.post(f'/workspaces/not-a-uuid/{action}',json=payload).status_code == 422

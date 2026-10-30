from fastapi.testclient import TestClient
from tenderready.config import Settings
from tenderready.site import create_site


def test_same_origin_site_keeps_api_private(database, tmp_path):
    engine, _ = database
    public = tmp_path / 'public'
    public.mkdir()
    (public / 'index.html').write_text('<h1>TenderReady</h1>')
    token = 'test-only-token-' * 3
    settings = Settings(app_env='production', app_api_token=token)
    with TestClient(create_site(settings, engine, public)) as client:
        assert client.get('/').status_code == 200
        assert 'TenderReady' in client.get('/').text
        assert client.get('/api/workspaces').status_code == 401
        assert client.get('/api/workspaces', headers={'Authorization': 'Bearer ' + token}).status_code == 200
        assert client.get('/.env').status_code == 404
        assert client.get('/data/documents/private.pdf').status_code == 404

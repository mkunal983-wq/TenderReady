import pytest
from fastapi.testclient import TestClient
from tenderready.api import create_app
from tenderready.config import Settings


@pytest.mark.parametrize('host', ['untrusted.invalid', 'untrusted.invalid:8000', 'localhost.untrusted.invalid', '127.0.0.1.untrusted.invalid'])
def test_loopback_socket_does_not_authorize_untrusted_host(database, host):
    engine,_=database
    settings=Settings(_env_file=None,app_api_token='')
    with TestClient(create_app(settings,engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
        assert c.get('/ready').status_code==200
        response=c.get('/workspaces',headers={'Host':host})
        assert response.status_code==403
        assert response.json()['error']['code']=='forbidden'
        assert c.post('/workspaces',headers={'Host':host},json={'title':'Should not create','supplier_name':'X'}).status_code==403
        assert c.get('/workspaces').json()==[]


@pytest.mark.parametrize('host', ['localhost:8000', '127.0.0.1:8000', '[::1]:8000'])
def test_valid_loopback_hosts_remain_available(database, host):
    engine,_=database
    with TestClient(create_app(Settings(_env_file=None,app_api_token=''),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
        assert c.get('/ready',headers={'Host':host}).status_code==200


def test_forged_forwarding_headers_do_not_override_host_or_peer(database):
    engine,_=database
    with TestClient(create_app(Settings(_env_file=None,app_api_token=''),engine),base_url='http://untrusted.invalid',client=('192.0.2.1',1)) as c:
        assert c.get('/workspaces',headers={'X-Forwarded-For':'127.0.0.1','X-Forwarded-Host':'localhost'}).status_code==403


def test_sqlite_tender_text_is_owner_only(database):
    import os
    from pathlib import Path
    engine,_=database
    if os.name != 'posix':
        pytest.skip('POSIX file-mode check; Windows needs filesystem ACLs')
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar()==1
    assert Path(engine.url.database).stat().st_mode & 0o777 == 0o600

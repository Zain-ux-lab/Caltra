import base64
from starlette.requests import Request
from backend.access import check_access

def request(host='caltra.example',path='/',auth='',origin='',method='GET'):
    return Request({'type':'http','method':method,'scheme':'https','server':(host,443),'path':path,'query_string':b'','headers':[(b'host',host.encode()),(b'authorization',auth.encode()),(b'origin',origin.encode())]})

def test_cloud_private_and_same_origin(monkeypatch):
    monkeypatch.setenv('CALTRA_PUBLIC_ORIGIN','https://caltra.example')
    monkeypatch.setenv('CALTRA_ACCESS_PASSWORD','long-private-test-password')
    assert check_access(request()).status_code==401
    auth='Basic '+base64.b64encode(b'caltra:long-private-test-password').decode()
    assert check_access(request(auth=auth)) is None
    assert check_access(request(auth=auth,method='POST',origin='https://evil.example')).status_code==403
    assert check_access(request(path='/healthz')) is None
    assert check_access(request(host='evil.example',auth=auth)).status_code==403

def test_cloud_fails_closed(monkeypatch):
    monkeypatch.setenv('CALTRA_PUBLIC_ORIGIN','https://caltra.example')
    monkeypatch.delenv('CALTRA_ACCESS_PASSWORD',raising=False)
    assert check_access(request()).status_code==503

def test_local_stays_local(monkeypatch):
    monkeypatch.delenv('CALTRA_PUBLIC_ORIGIN',raising=False)
    assert check_access(request()).status_code==403
    assert check_access(request(host='localhost')) is None

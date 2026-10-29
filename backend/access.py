"""Private single-user cloud beta access. Local development stays local-only."""
import base64
import hmac
import os
from fastapi.responses import JSONResponse

def check_access(request):
    cloud=os.getenv('CALTRA_PUBLIC_ORIGIN','').rstrip('/')
    host=request.url.hostname
    if not cloud:
        if host not in {'127.0.0.1','localhost','testserver'}:
            return JSONResponse({'detail':'This prototype is local only.'},403)
        allowed={f'http://{host}:{port}' for port in (8000,5173,8765)}
    else:
        from urllib.parse import urlsplit
        parsed=urlsplit(cloud)
        password=os.getenv('CALTRA_ACCESS_PASSWORD','')
        if parsed.scheme!='https' or len(password)<16:
            return JSONResponse({'detail':'Private cloud access is not configured.'},503)
        if host!=parsed.hostname:return JSONResponse({'detail':'Invalid host.'},403)
        allowed={cloud}
        if request.url.path=='/healthz' and request.method=='GET':return None
        try:
            scheme,encoded=request.headers.get('authorization','').split(' ',1)
            credentials=base64.b64decode(encoded,validate=True).decode()
        except (ValueError,UnicodeError):credentials='';scheme=''
        expected='caltra:'+password
        if scheme.lower()!='basic' or not hmac.compare_digest(credentials.encode(),expected.encode()):
            return JSONResponse({'detail':'Sign in to Caltra.'},401,headers={'WWW-Authenticate':'Basic realm="Caltra", charset="UTF-8"','Cache-Control':'no-store'})
    origin=request.headers.get('origin')
    if request.method not in {'GET','HEAD','OPTIONS'} and origin and origin not in allowed:
        return JSONResponse({'detail':'Foreign origin rejected.'},403)
    return None

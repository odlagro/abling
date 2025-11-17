import time, os, requests
from base64 import b64encode

AUTH_URL='https://www.bling.com.br/b/Api/v3/oauth/authorize'
TOKEN_URL='https://www.bling.com.br/b/Api/v3/oauth/token'
API_BASE='https://api.bling.com.br/Api/v3'

def _basic_auth_header(cid, csec):
    return "Basic " + b64encode(f"{cid}:{csec}".encode()).decode()

class BlingAPI:
    def __init__(self, client_id, client_secret, redirect_uri, session_store):
        self.client_id=client_id; self.client_secret=client_secret; self.redirect_uri=redirect_uri; self.session=session_store
        os.makedirs('cache', exist_ok=True)

    def auth_url(self, state='ablingv1'):
        from urllib.parse import urlencode
        q={'response_type':'code','client_id':self.client_id,'redirect_uri':self.redirect_uri,'state':state}
        return AUTH_URL+'?'+urlencode(q)

    def _post_token(self, data):
        headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded','Authorization':_basic_auth_header(self.client_id,self.client_secret)}
        return requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)

    def exchange_code(self, code):
        r=self._post_token({'grant_type':'authorization_code','code':code,'redirect_uri':self.redirect_uri}); r.raise_for_status()
        tok=r.json(); self.session['bling_token']=tok; self.session['bling_token_ts']=int(time.time()); return tok

    def refresh_token(self):
        tok=self.session.get('bling_token',{}); ref=tok.get('refresh_token')
        if not ref: return None
        r=self._post_token({'grant_type':'refresh_token','refresh_token':ref})
        if r.status_code!=200: return None
        new=r.json(); self.session['bling_token']=new; self.session['bling_token_ts']=int(time.time()); return new

    def _auth(self):
        tok=self.session.get('bling_token',{}).get('access_token')
        return {'Authorization': f'Bearer {tok}','Accept':'application/json'} if tok else {'Accept':'application/json'}

    def _get(self, path, params=None):
        import requests
        return requests.get(API_BASE+path, headers=self._auth(), params=params or {}, timeout=60)

    def list_sales(self, data_ini, data_fim, situacao=None, pagina=1, limite=50):
        q={'pagina':pagina,'limite':limite,'dataEmissao[ini]':data_ini,'dataEmissao[fim]':data_fim}
        if situacao: q['situacao']=situacao
        r=self._get('/pedidos/vendas', q)
        if r.status_code==401 and self.refresh_token():
            r=self._get('/pedidos/vendas', q)
        r.raise_for_status(); return r.json()

    def get_sale(self, pid):
        r=self._get(f'/pedidos/vendas/{pid}')
        if r.status_code==401 and self.refresh_token():
            r=self._get(f'/pedidos/vendas/{pid}')
        if r.status_code!=200: return None
        try: return r.json().get('data')
        except Exception: return None

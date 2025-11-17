
import requests, time, json

BLING_TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
BLING_API_BASE = "https://api.bling.com.br/Api/v3"

def _safe_json(resp):
    """Best-effort JSON parse with graceful fallback and helpful error."""
    try:
        return resp.json()
    except Exception:
        txt = resp.text or ""
        i = txt.find("{")
        j = txt.rfind("}")
        if i != -1 and j != -1 and j > i:
            chunk = txt[i:j+1]
            try:
                return json.loads(chunk)
            except Exception:
                pass
        snippet = (txt[:400] if isinstance(txt, str) else str(txt)).replace("\n", "\\n").replace("\r", "")
        raise Exception(f"JSON inválido (status {resp.status_code}). Início da resposta: {snippet}")

class BlingAPI:
    def __init__(self, client_id, client_secret, redirect_uri, token=None, token_saver=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token = token or {}
        self.token_saver = token_saver

    def _headers(self):
        self._ensure_valid_token()
        return {
            "Authorization": f"Bearer {self.token.get('access_token')}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _ensure_valid_token(self):
        expires_in = self.token.get("expires_in")
        created_at = self.token.get("created_at")
        if expires_in and created_at:
            now = int(time.time())
            if now > int(created_at) + int(expires_in) - 60:
                self.refresh_token()

    def exchange_code_for_token(self, code: str):
        auth = (self.client_id, self.client_secret)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        resp = requests.post(BLING_TOKEN_URL, data=data, auth=auth, timeout=30)
        if resp.status_code >= 400:
            raise Exception(f"Token error: {resp.status_code} {resp.text}")
        tok = _safe_json(resp)
        tok["created_at"] = int(time.time())
        if self.token_saver:
            self.token_saver(tok)
        self.token = tok
        return tok

    def refresh_token(self):
        refresh = self.token.get("refresh_token")
        if not refresh:
            raise Exception("Refresh token ausente. Refaça a conexão.")
        auth = (self.client_id, self.client_secret)
        data = {"grant_type": "refresh_token", "refresh_token": refresh}
        resp = requests.post(BLING_TOKEN_URL, data=data, auth=auth, timeout=30)
        if resp.status_code >= 400:
            raise Exception(f"Refresh error: {resp.status_code} {resp.text}")
        tok = _safe_json(resp)
        tok["created_at"] = int(time.time())
        if self.token_saver:
            self.token_saver(tok)
        self.token = tok
        return tok

    def get_orders(self, pagina=1, limite=100, params_extra=None):
        params = {"pagina": pagina, "limite": limite}
        if params_extra:
            params.update(params_extra)
        url = f"{BLING_API_BASE}/pedidos/vendas"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=60)
        if resp.status_code >= 400:
            raise Exception(f"GET /pedidos/vendas falhou: {resp.status_code} {resp.text}")
        return _safe_json(resp)

    def get_order(self, pedido_id):
        url = f"{BLING_API_BASE}/pedidos/vendas/{pedido_id}"
        resp = requests.get(url, headers=self._headers(), timeout=60)
        if resp.status_code >= 400:
            raise Exception(f"GET /pedidos/vendas/{pedido_id} falhou: {resp.status_code} {resp.text}")
        return _safe_json(resp)

    def get_sellers(self, pagina=1, limite=500):
        """Lista vendedores para resolver nome por id/código."""
        params = {"pagina": pagina, "limite": limite}
        url = f"{BLING_API_BASE}/vendedores"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=60)
        if resp.status_code >= 400:
            raise Exception(f"GET /vendedores falhou: {resp.status_code} {resp.text}")
        return _safe_json(resp)

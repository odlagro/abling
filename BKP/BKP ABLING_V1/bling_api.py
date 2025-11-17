import time, json
from typing import Dict, List, Optional, Tuple, Any
import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://www.bling.com.br/Api/v3"

class BlingAPIError(Exception):
    pass

class BlingAPI:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, tokens: Optional[Dict]=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.tokens = tokens or {}
        self._vendor_cache: Dict[int, Dict] = {}
        self._vendor_ttl = 6 * 60 * 60
        self._situacao_map: Optional[Dict[int, str]] = None

    # -------------------- internal helpers --------------------
    def _headers(self):
        if not self.tokens.get("access_token"):
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _raise_for_response(self, resp: requests.Response):
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = {"error": {"type": "HTTP_ERROR", "message": resp.text}}
            msg = f"HTTP {resp.status_code} - {json.dumps(payload)}"
            if resp.status_code == 403:
                msg += " | Dica: no App Bling, habilite os escopos necessários (Pedidos, Vendedores e Situações) e reconecte."
            raise BlingAPIError(msg)

    # -------------------- OAuth --------------------
    def exchange_code_for_tokens(self, code: str) -> Dict:
        url = f"{API_BASE}/oauth/token"
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri}
        resp = requests.post(url, data=data, auth=HTTPBasicAuth(self.client_id, self.client_secret), timeout=30)
        self._raise_for_response(resp)
        data = resp.json()
        data["obtained_at"] = time.time()
        self.tokens = data
        return data

    def ensure_token(self):
        if not self.tokens.get("access_token"):
            raise BlingAPIError("Sem access_token. Clique em Conectar ao Bling.")
        obtained = self.tokens.get("obtained_at", 0)
        expires = self.tokens.get("expires_in", 0)
        if obtained and expires and time.time() > (obtained + expires - 300):
            self.refresh_tokens()

    def refresh_tokens(self):
        if not self.tokens.get("refresh_token"):
            raise BlingAPIError("Sem refresh_token para renovar.")
        url = f"{API_BASE}/oauth/token"
        data = {"grant_type": "refresh_token", "refresh_token": self.tokens["refresh_token"]}
        resp = requests.post(url, data=data, auth=HTTPBasicAuth(self.client_id, self.client_secret), timeout=30)
        self._raise_for_response(resp)
        data = resp.json()
        data["obtained_at"] = time.time()
        self.tokens.update(data)
        return self.tokens

    def revoke_access_token(self, access_token: str):
        url = f"{API_BASE}/oauth/revoke"
        data = {"token": access_token, "token_type_hint": "access_token"}
        requests.post(url, data=data, auth=HTTPBasicAuth(self.client_id, self.client_secret), timeout=30)

    def revoke_refresh_token(self, refresh_token: str):
        url = f"{API_BASE}/oauth/revoke"
        data = {"token": refresh_token, "token_type_hint": "refresh_token"}
        requests.post(url, data=data, auth=HTTPBasicAuth(self.client_id, self.client_secret), timeout=30)

    # -------------------- Situações --------------------
    def _load_situacao_map(self) -> Dict[int, str]:
        if self._situacao_map is not None:
            return self._situacao_map
        try:
            url_mod = f"{API_BASE}/situacoes/modulos"
            resp = requests.get(url_mod, headers=self._headers(), timeout=30)
            self._raise_for_response(resp)
            mod_data = resp.json().get("data") or resp.json().get("body") or []
            modulo_id = None
            for m in mod_data:
                nome = (m.get("nome") or m.get("descricao") or "").lower()
                if "pedido" in nome and "venda" in nome:
                    modulo_id = m.get("id")
                    break
            if not modulo_id and mod_data:
                modulo_id = mod_data[0].get("id")
            situ_map: Dict[int, str] = {}
            if modulo_id:
                url_sit = f"{API_BASE}/situacoes/modulos/{modulo_id}"
                s_resp = requests.get(url_sit, headers=self._headers(), timeout=30)
                self._raise_for_response(s_resp)
                sit_list = s_resp.json().get("data") or s_resp.json().get("body") or []
                for s in sit_list:
                    sid = s.get("id")
                    nome = s.get("nome") or s.get("descricao") or ""
                    if sid is not None:
                        try:
                            situ_map[int(sid)] = nome
                        except Exception:
                            pass
            self._situacao_map = situ_map
            return situ_map
        except Exception as e:
            if "HTTP 403" in str(e) or "insufficient_scope" in str(e):
                self._situacao_map = {}
                return self._situacao_map
            raise

    def situacao_nome(self, situacao_obj) -> str:
        if isinstance(situacao_obj, dict):
            sid = situacao_obj.get("id")
            if isinstance(sid, (int, float)) or (isinstance(sid, str) and str(sid).isdigit()):
                sid = int(sid)
                nome = self._load_situacao_map().get(sid)
                return nome or situacao_obj.get("nome") or situacao_obj.get("descricao") or ""
            return situacao_obj.get("nome") or situacao_obj.get("descricao") or ""
        if isinstance(situacao_obj, (int, float)) or (isinstance(situacao_obj, str) and str(situacao_obj).isdigit()):
            sid = int(situacao_obj)
            return self._load_situacao_map().get(sid, "")
        if isinstance(situacao_obj, str):
            return situacao_obj
        return ""

    # -------------------- Vendedores --------------------
    def list_vendedores(self, page: int = 1, max_pages: int = 5):
        vendedores = []
        vendor_map = {}
        current = page
        while current <= max_pages:
            params = {"pagina": current, "limite": 100}
            url = f"{API_BASE}/vendedores"
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            self._raise_for_response(resp)
            payload = resp.json()
            body = payload.get("data") or payload.get("body") or []
            if not body:
                break
            for v in body:
                contato = v.get("contato") or {}
                contato_id = contato.get("id")
                contato_nome = contato.get("nome")
                top_id = v.get("id")
                top_nome = v.get("nome") or v.get("name")
                nome_final = top_nome or contato_nome or "Sem nome"
                vendedores.append(v)
                for key in (top_id, contato_id):
                    if isinstance(key, (int, float)) or (isinstance(key, str) and str(key).isdigit()):
                        key = int(key)
                        vendor_map[key] = nome_final
                        self._vendor_cache[key] = {"name": nome_final, "ts": time.time()}
            meta = payload.get("page") or payload.get("meta") or {}
            total_paginas = meta.get("totalPages") or meta.get("total_paginas") or 1
            try:
                total_paginas = int(total_paginas)
            except Exception:
                total_paginas = 1
            if current >= total_paginas:
                break
            current += 1
        return vendedores, vendor_map

    def get_vendedor_nome(self, vendedor_id: int):
        if not vendedor_id:
            return None
        now = time.time()
        hit = self._vendor_cache.get(vendedor_id)
        if hit and now - hit["ts"] < self._vendor_ttl:
            return hit["name"]
        try:
            url = f"{API_BASE}/vendedores/{int(vendedor_id)}"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            self._raise_for_response(resp)
            d = resp.json().get("data") or resp.json().get("body") or {}
            name = d.get("nome") or d.get("name") or (d.get("contato") or {}).get("nome") or "Sem nome"
            self._vendor_cache[vendedor_id] = {"name": name, "ts": now}
            contato_id = (d.get("contato") or {}).get("id")
            if isinstance(contato_id, (int, float)) or (isinstance(contato_id, str) and str(contato_id).isdigit()):
                self._vendor_cache[int(contato_id)] = {"name": name, "ts": now}
            return name
        except Exception as e:
            if "HTTP 403" in str(e) or "insufficient_scope" in str(e):
                self._vendor_cache[vendedor_id] = {"name": "Sem nome", "ts": now}
                return "Sem nome"
            raise

    # -------------------- Pedidos --------------------
    def _extract_vendor(self, vendedor_field: Any, item: Dict) -> Tuple[Optional[int], str]:
        label = ""
        vid = None
        if isinstance(vendedor_field, dict):
            label = json.dumps(vendedor_field, ensure_ascii=False)[:140]
            vid = vendedor_field.get("id")
            if not vid:
                vid = (vendedor_field.get("contato") or {}).get("id")
        elif isinstance(vendedor_field, (int, float)) or (isinstance(vendedor_field, str) and str(vendedor_field).isdigit()):
            vid = int(vendedor_field)
            label = str(vendedor_field)
        elif isinstance(vendedor_field, str) and vendedor_field.strip():
            label = vendedor_field.strip()
        if not vid and isinstance(item, dict):
            for k in ("idVendedor", "vendedorId", "id_vendedor"):
                if item.get(k):
                    if isinstance(item[k], (int, float)) or (isinstance(item[k], str) and str(item[k]).isdigit()):
                        vid = int(item[k])
                        label = f"{k}={item[k]}"
                    else:
                        label = f"{k}={item[k]}"
        return vid, label

    def list_pedidos(self, status_id: str = None, page: int = 1, max_pages: int = 5, date_from: str = None, date_to: str = None):
        pedidos = []
        current_page = page
        situ_map = self._load_situacao_map()
        while current_page <= max_pages:
            params = {"pagina": current_page, "limite": 100}
            if status_id:
                params["idsSituacoes[]"] = status_id
            if date_from:
                params["dataEmissaoInicial"] = date_from
                params["dataInicial"] = date_from
                params["dataEmissao[de]"] = date_from
            if date_to:
                params["dataEmissaoFinal"] = date_to
                params["dataFinal"] = date_to
                params["dataEmissao[ate]"] = date_to
            url = f"{API_BASE}/pedidos/vendas"
            resp = requests.get(url, headers=self._headers(), params=params, timeout=60)
            self._raise_for_response(resp)
            payload = resp.json()
            body = payload.get("body") or payload.get("data") or []
            if not body:
                break
            for item in body:
                situ = item.get("situacao")
                vendedor = item.get("vendedor")
                vendedor_id, vendedor_lbl = self._extract_vendor(vendedor, item)
                status_nome = self.situacao_nome(situ)
                pedidos.append({
                    "id": item.get("id"),
                    "numero": item.get("numero") or (item.get("loja") or {}).get("numero"),
                    "data": item.get("data") or item.get("dataPrevista"),
                    "status_nome": status_nome,
                    "status_id": (situ.get("id") if isinstance(situ, dict) else (situ if isinstance(situ,(int,str)) else None)),
                    "cliente_nome": (item.get("contato") or {}).get("nome"),
                    "total": item.get("total"),
                    "vendedor_id": vendedor_id,
                    "vendedor_label": vendedor_lbl,
                    "vendedor_nome": None,
                })
            meta = payload.get("page") or payload.get("meta") or {}
            total_paginas = meta.get("totalPages") or meta.get("total_paginas") or 1
            try:
                total_paginas = int(total_paginas)
            except Exception:
                total_paginas = 1
            if current_page >= total_paginas:
                break
            current_page += 1
            time.sleep(0.2)
        return pedidos, situ_map

    def get_pedido_itens(self, pedido_id: int):
        url = f"{API_BASE}/pedidos/vendas/{pedido_id}"
        resp = requests.get(url, headers=self._headers(), timeout=60)
        self._raise_for_response(resp)
        data = resp.json()
        body = data.get("body") or data.get("data") or {}
        itens = body.get("itens") or []
        out = []
        if isinstance(itens, list):
            for i, it in enumerate(itens, 1):
                out.append({
                    "n": i,
                    "nome": (it.get("produto") or {}).get("nome") or it.get("descricao") or "",
                    "sku": (it.get("produto") or {}).get("codigo") or (it.get("produto") or {}).get("sku") or "",
                    "quantidade": it.get("quantidade") or it.get("qtde") or 1,
                    "preco": it.get("valor") or it.get("preco") or 0,
                })
        return out

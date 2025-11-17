# frete_blueprint.py
# Blueprint "frete" para integrar no ApoioV sem quebrar nada.
# Expõe:
#   GET /api/ufs           -> lista de UFs
#   GET /api/frete?uf=XX   -> valor do frete para a UF
#
# Usa leitura direta da guia FRETE do Google Sheets via CSV público.
# Mantém cache em memória para reduzir latência.
#
# Integração:
#   from frete_blueprint import frete_bp
#   app.register_blueprint(frete_bp)
#
from flask import Blueprint, jsonify, current_app, request
import os, time, csv, io, requests

frete_bp = Blueprint("frete", __name__)

SHEET_ID = os.getenv("FRETE_SHEET_ID", "1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg")
FRETE_GID = os.getenv("FRETE_GID", "117017797")
CSV_URL = "https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={FRETE_GID}"

CACHE_TTL_SECONDS = int(os.getenv("FRETE_CACHE_TTL", "1800"))  # 30min default
_cache = {"timestamp": 0.0, "uf2frete": {}, "ufs": []}

EXPECTED_UF_LIST = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA",
    "PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"
]

def _normalize_header(h):
    return (h or "").strip().lower()

def _to_float(s):
    if s is None: return None
    txt = str(s).strip()
    if not txt: return None
    # aceita formatos com vírgula e com R$
    txt = txt.replace("R$", "").replace(" ", "")
    # remove separador de milhar "." e converte vírgula para ponto
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return None

def _fetch_from_sheet():
    url = CSV_URL.format(SHEET_ID=SHEET_ID, FRETE_GID=FRETE_GID)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8", errors="ignore"))))
    if not rows:
        return {}, []
    headers = [_normalize_header(h) for h in rows[0]]
    # detecta colunas
    uf_idx = None
    for k in ("uf", "estado", "sigla"):
        if k in headers:
            uf_idx = headers.index(k)
            break
    frete_idx = None
    for k in ("frete", "valor", "preco", "preço", "valor_frete", "vl_frete"):
        if k in headers:
            frete_idx = headers.index(k)
            break
    # fallback heurístico
    if uf_idx is None:
        uf_idx = 0 if len(headers) >= 1 else None
    if frete_idx is None:
        frete_idx = 1 if len(headers) >= 2 else None
    if uf_idx is None or frete_idx is None:
        return {}, []
    mapping = {}
    ufs = []
    for r in rows[1:]:
        if len(r) <= max(uf_idx, frete_idx): 
            continue
        uf = (r[uf_idx] or "").strip().upper()
        if len(uf) != 2:
            continue
        val = _to_float(r[frete_idx])
        if val is None:
            continue
        mapping[uf] = val
        if uf not in ufs:
            ufs.append(uf)
    if not ufs:
        ufs = EXPECTED_UF_LIST
    return mapping, sorted(ufs)

def _ensure_cache():
    now = time.time()
    if (now - _cache["timestamp"]) > CACHE_TTL_SECONDS or not _cache["uf2frete"]:
        try:
            m, ufs = _fetch_from_sheet()
            if m:
                _cache["uf2frete"] = m
                _cache["ufs"] = ufs or EXPECTED_UF_LIST
                _cache["timestamp"] = now
        except Exception as e:
            current_app.logger.error(f"[FRETE] Falha ao baixar planilha: {e}")
            if not _cache["ufs"]:
                _cache["ufs"] = EXPECTED_UF_LIST

@frete_bp.get("/api/ufs")
def api_ufs():
    _ensure_cache()
    return jsonify({"ok": True, "ufs": _cache["ufs"] or EXPECTED_UF_LIST})

@frete_bp.get("/api/frete")
def api_frete():
    uf = (request.args.get("uf") or "").strip().upper()
    if not uf:
        return jsonify({"ok": False, "error": "UF não informada"}), 400
    _ensure_cache()
    val = _cache["uf2frete"].get(uf)
    if val is None:
        return jsonify({"ok": False, "error": f"UF '{uf}' não encontrada na guia FRETE"}), 404
    return jsonify({"ok": True, "uf": uf, "frete": val})

import os, time, json
from urllib.parse import urlencode
from datetime import date, timedelta, datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from dotenv import load_dotenv
from bling_api import BlingAPI, BlingAPIError

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-please")

CLIENT_ID = os.environ.get("BLING_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("BLING_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("BLING_REDIRECT_URI", "http://127.0.0.1:5050/callback")
TOKENS_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")

def save_tokens(tokens: dict):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

def load_tokens() -> dict:
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def delete_tokens():
    if os.path.exists(TOKENS_FILE):
        os.remove(TOKENS_FILE)

@app.template_filter("currency")
def currency(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)

@app.template_filter('fmt_date')
def fmt_date(value: str):
    if not value:
        return ''
    s = str(value)
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            d = datetime.strptime(s[:19], fmt)
            return d.strftime('%d/%m/%y')
        except Exception:
            pass
    return s

def get_api() -> BlingAPI:
    return BlingAPI(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, load_tokens())

def calc_total(pedidos):
    tot = 0.0
    for p in pedidos:
        try:
            tot += float(p.get("total") or 0)
        except Exception:
            pass
    return tot

@app.route("/auth")
def auth():
    if not CLIENT_ID or not CLIENT_SECRET:
        flash("BLING_CLIENT_ID/BLING_CLIENT_SECRET ausentes no .env.", "danger")
        return redirect(url_for("index"))
    state = os.urandom(8).hex()
    session["oauth_state"] = state
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "state": state,
        "redirect_uri": REDIRECT_URI
    }
    return redirect(f"https://www.bling.com.br/Api/v3/oauth/authorize?{urlencode(params)}")

@app.route("/callback")
def callback():
    if "error" in request.args:
        err = request.args.get("error_description", request.args.get("error"))
        flash(f"Erro vindo do Bling: {err}", "danger")
        return redirect(url_for("index"))
    code = request.args.get("code")
    api = get_api()
    try:
        tokens = api.exchange_code_for_tokens(code)
        save_tokens(tokens)
        flash("Conectado ao Bling com sucesso!", "success")
    except BlingAPIError as e:
        flash(f"Falha ao obter token: {e}", "danger")
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    tokens = load_tokens()
    api = get_api()
    if tokens.get("access_token"):
        try:
            api.revoke_access_token(tokens["access_token"])
        except Exception:
            pass
    if tokens.get("refresh_token"):
        try:
            api.revoke_refresh_token(tokens["refresh_token"])
        except Exception:
            pass
    delete_tokens()
    flash("Tokens removidos.", "info")
    return redirect(url_for("index"))

@app.route("/ping_api")
def ping_api():
    tokens = load_tokens()
    connected = bool(tokens.get("access_token"))
    return jsonify({
        "ok": True,
        "connected": connected,
        "has_refresh_token": bool(tokens.get("refresh_token")),
        "token_expires_at": tokens.get("obtained_at", 0) + tokens.get("expires_in", 0) if tokens else None
    })

@app.route("/diagnostico")
def diagnostico():
    tokens = load_tokens()
    return jsonify({
        "connected": bool(tokens.get("access_token")),
        "has_refresh_token": bool(tokens.get("refresh_token")),
        "raw_tokens": tokens
    })

@app.route("/vendedores")
def vendedores():
    api = get_api()
    try:
        api.ensure_token()
        vendedores, vendor_map = api.list_vendedores(max_pages=5)
        return jsonify({"ok": True, "qtd": len(vendedores), "exemplo_primeiros": vendedores[:10], "mapa_ids": list(vendor_map.items())[:10]})
    except BlingAPIError as e:
        return jsonify({"ok": False, "erro": str(e)}), 400

@app.route("/", methods=["GET"])
def index():
    status_id = request.args.get("status_id") or None
    today = date.today()
    date_from = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')

    api = get_api()
    pedidos = []
    situ_map = {}
    api_failed = False
    api_error_detail = ""
    try:
        api.ensure_token()
        pedidos, situ_map = api.list_pedidos(status_id=status_id, max_pages=10, date_from=date_from, date_to=date_to)
        try:
            _vendedores, vendor_map = api.list_vendedores(max_pages=5)
        except BlingAPIError:
            vendor_map = {}
        # preencher vendedor_nome e itens de cada pedido
        for p in pedidos:
            if p.get("vendedor_id"):
                try:
                    vid_int = int(p["vendedor_id"])
                    p["vendedor_nome"] = vendor_map.get(vid_int) or api.get_vendedor_nome(vid_int) or "Sem nome"
                except BlingAPIError:
                    p["vendedor_nome"] = "Sem nome"
            else:
                p["vendedor_nome"] = "Sem nome"
            try:
                p["itens"] = api.get_pedido_itens(p["id"])
                time.sleep(0.2)
            except BlingAPIError as e:
                p["itens"] = []
                p["_itens_error"] = str(e)
    except BlingAPIError as e:
        api_failed = True
        api_error_detail = str(e)

    return render_template(
        "index.html",
        connected=bool(load_tokens().get("access_token")),
        status_id=(str(status_id) if status_id else ''),
        pedidos=pedidos,
        situ_map=situ_map,
        total_pedidos=len(pedidos),
        valor_total=calc_total(pedidos),
        api_failed=api_failed,
        api_error_detail=api_error_detail,
        date_from=date_from,
        date_to=date_to
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[ABLING] Iniciando Flask em http://127.0.0.1:{port} (Ctrl+C para sair)")
    app.run(host="0.0.0.0", port=port, debug=False)

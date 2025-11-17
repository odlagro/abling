from __future__ import annotations
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Flask, render_template, redirect, request, session, url_for, flash
from config import settings
from bling import BlingAPI
import json
from collections import defaultdict
import os
import io
import csv
import requests

app = Flask(__name__)
app.secret_key = settings.FLASK_SECRET_KEY

# ================== MAPAS ==================
STATUS_MAP = {
    56035: 'AGUARDANDO SEPARAÇÃO',
    6: 'EM ABERTO',
    466202: 'ENVIO ESTOQUE FULL',
    12: 'CANCELADO',
    9: 'ATENDIDO',
    67578: 'ENTREGUE',
    446927: 'SEPARADO AGUARD. COLETA',
    21: 'EM DIGITAÇÃO',
    67577: 'ENVIADO'
}
VENDEDOR_MAP = {
    15596309360: 'WENIO',
    15596488325: 'JOICE',
    4664550185: 'MERCADO LIVRE',
    14402874266: 'RANGEL'
}
FORMAPAG_MAP = {
    2515978: 'CONTA A RECEBER',
    1917260: 'PAGAR.ME',
    554129: 'CONTA A RECEBER'
}

# ================== CACHES ==================
MONTH_STATUS_CACHE = {}
MONTH_VENDOR_CACHE = {}
MONTH_DAY_CACHE = {}
MONTH_PROD_CACHE = {}   # produtos no mês
PAGE_SNAPSHOT = {}
# ============================================

# ================== CONFIG LOCAL (PLANILHA ANÁLISE) ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_CONFIG_FILE = os.path.join(BASE_DIR, 'sheet_config.json')


def load_sheet_config() -> dict:
    try:
        if not os.path.exists(SHEET_CONFIG_FILE):
            return {}
        with open(SHEET_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_sheet_config(analysis_sheet_url: str) -> None:
    cfg = load_sheet_config()
    cfg['analysis_sheet_url'] = analysis_sheet_url.strip()
    with open(SHEET_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_analysis_sheet_url() -> str | None:
    cfg = load_sheet_config()
    return cfg.get('analysis_sheet_url')


def build_csv_url_from_sheet(sheet_url: str) -> str | None:
    """
    Converte:
    https://docs.google.com/spreadsheets/d/<ID>/edit?gid=821374399#gid=821374399
    para:
    https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=821374399
    """
    try:
        if '/d/' not in sheet_url:
            return None
        parts = sheet_url.split('/d/')
        rest = parts[1]
        sheet_id = rest.split('/')[0]
        gid = '0'
        if 'gid=' in sheet_url:
            gid = sheet_url.split('gid=')[1].split('&')[0].split('#')[0]
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    except Exception:
        return None


def load_margin_map_from_sheet(sheet_url: str) -> dict[str, str]:
    """
    Lê a planilha de análise de vendas em CSV e monta um mapa:
      numero_pedido (coluna D) -> margem_lucro (coluna T)

    Colunas:
      D -> índice 3
      T -> índice 19
    """
    csv_url = build_csv_url_from_sheet(sheet_url)
    if not csv_url:
        raise ValueError('URL da planilha de análise inválida.')

    resp = requests.get(csv_url, timeout=20)
    resp.raise_for_status()

    text = resp.text
    margin_map: dict[str, str] = {}
    reader = csv.reader(io.StringIO(text))
    for idx, row in enumerate(reader):
        # pula cabeçalho
        if idx == 0:
            continue
        if len(row) <= 19:
            continue
        numero_pedido = (row[3] or '').strip()   # coluna D
        margem = (row[19] or '').strip()         # coluna T
        if numero_pedido:
            margin_map[numero_pedido] = margem
    return margin_map
# =====================================================================


# --------------- UTILIDADES -----------------
def default_dates():
    try:
        tz = ZoneInfo('America/Sao_Paulo')
        today = datetime.now(tz).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()
    return today - timedelta(days=2), today


def month_bounds_today():
    try:
        tz = ZoneInfo('America/Sao_Paulo')
        today = datetime.now(tz).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()
    return date(today.year, today.month, 1), today


def to_iso(d):
    if isinstance(d, datetime):
        d = d.date()
    return d.isoformat()


def first(d, keys):
    for k in keys:
        if not k:
            continue
        if '.' in k:
            cur = d
            ok = True
            for part in k.split('.'):
                if isinstance(cur, dict) and part in cur:
                    cur = cur.get(part)
                else:
                    ok = False
                    break
            if ok and cur not in (None, ''):
                return cur
        else:
            v = d.get(k)
            if v not in (None, ''):
                return v
    return None


def br_dmy_short(s):
    if not s:
        return '-'
    s = str(s)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
        try:
            d = datetime.strptime(s[:10], fmt)
            return d.strftime('%d/%m/%y')
        except Exception:
            pass
    return s


def parse_date(s):
    if not s:
        return None
    s = str(s)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except Exception:
            continue
    return None


def brl(v):
    try:
        v = float(v or 0)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_total(raw) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_qty(q):
    try:
        return float(q)
    except Exception:
        try:
            return float(str(q).replace(',', '.'))
        except Exception:
            return 0.0


def normalize_item(i):
    prod = i.get('produto') or {}
    nome = prod.get('nome') or i.get('descricao') or '-'
    sku = prod.get('codigo') or i.get('codigo') or '-'
    qtd = parse_qty(i.get('quantidade') or 0)
    preco = i.get('valor') or 0
    try:
        preco = float(preco)
    except Exception:
        try:
            preco = float(str(preco).replace(',', '.'))
        except Exception:
            preco = 0.0
    return {'_nome': nome, '_sku': sku, '_qtd': qtd, '_preco': preco}


def api():
    return BlingAPI(settings.BLING_CLIENT_ID,
                    settings.BLING_CLIENT_SECRET,
                    settings.BLING_REDIRECT_URI,
                    session)


@app.template_filter('brl')
def jinja_brl(v):
    return brl(v)


# Horário SP
def br_now_saopaulo():
    try:
        return datetime.now(ZoneInfo('America/Sao_Paulo'))
    except Exception:
        return datetime.now()


def fmt_br_min(dt: datetime) -> str:
    try:
        dt = dt.astimezone(ZoneInfo('America/Sao_Paulo'))
    except Exception:
        pass
    return dt.strftime('%d/%m %H:%M')
# ---------------------------------------------


# --------------- DIÁRIO (3 dias) --------------
def build_daily_panels(pedidos):
    from collections import defaultdict as dd
    por_dia_vend = dd(lambda: dd(lambda: {'qtd': 0, 'valor': 0.0}))
    detalhes_por_dia_vend = dd(list)
    vendedores_fixos = ['MERCADO LIVRE', 'WENIO', 'JOICE', 'RANGEL']

    for p in pedidos:
        dia_br = p.get('_data_emissao_br')
        if not dia_br or dia_br == '-':
            continue
        try:
            dia_key = datetime.strptime(dia_br, '%d/%m/%y').date()
        except Exception:
            continue

        vend = (p.get('_vendedor_display') or '-').upper().strip()
        if vend not in vendedores_fixos:
            vend = 'SEM VENDEDOR'

        raw_total = p.get('total')
        if raw_total is None:
            raw_total = (p.get('_raw_pair') or {}).get('detalhes', {}).get('total')
        valor = parse_total(raw_total)
        sid = p.get('_situacao_id')

        por_dia_vend[dia_key][vend]['qtd'] += 1
        por_dia_vend[dia_key][vend]['valor'] += valor

        detalhes_por_dia_vend[(dia_key, vend)].append({
            'numero': p.get('_numero') or p.get('numero') or p.get('id'),
            'data': dia_br,
            'total': valor,
            'sid': sid
        })

    dias_ordenados = sorted(list(por_dia_vend.keys()), reverse=True)[:3]

    vendor_panels = []
    for d in dias_ordenados:
        vendedores_list, total_qtd_dia, total_valor_dia = [], 0, 0.0
        for v in ['MERCADO LIVRE', 'WENIO', 'JOICE', 'RANGEL']:
            dados = por_dia_vend[d][v]
            q = int(dados['qtd'])
            val = float(dados['valor'])
            det = detalhes_por_dia_vend.get((d, v), [])
            has_cancel = any(x.get('sid') == 12 for x in det)
            vendedores_list.append({
                'nome': v,
                'qtd': q,
                'valor': val,
                'details': det,
                'has_cancelled': has_cancel,
                'detail_id': f"dv-{d.strftime('%Y%m%d')}-{v.replace(' ','_')}"
            })
            total_qtd_dia += q
            total_valor_dia += val
        vendor_panels.append({
            'dia_label': d.strftime('%d/%m/%y'),
            'dia_key': d.strftime('%Y-%m-%d'),
            'vendedores': vendedores_list,
            'total_qtd': total_qtd_dia,
            'total_valor': total_valor_dia
        })

    totais = {
        'qtd_pedidos': sum(d['total_qtd'] for d in vendor_panels),
        'valor_produtos': sum(d['total_valor'] for d in vendor_panels),
    }
    return vendor_panels, totais
# ----------------------------------------------


# --------- Assinaturas “mais recente” ----------
def newest_month_key(client, m_ini, m_fim):
    try:
        resp = client.list_sales(to_iso(m_ini), to_iso(m_fim), None, pagina=1, limite=1)
        data = resp.get('data') or []
        if not data:
            return ('none',)
        rec = data[0]
        pid = rec.get('id') or rec.get('numero') or '0'
        dem = first(rec, ['dataEmissao', 'data.emissao', 'data']) or ''
        return (str(pid), str(dem))
    except Exception:
        return None


def newest_range_key(client, d_ini, d_fim):
    try:
        resp = client.list_sales(to_iso(d_ini), to_iso(d_fim), None, pagina=1, limite=1)
        data = resp.get('data') or []
        if not data:
            return ('none',)
        rec = data[0]
        pid = rec.get('id') or rec.get('numero') or '0'
        dem = first(rec, ['dataEmissao', 'data.emissao', 'data']) or ''
        return (str(pid), str(dem))
    except Exception:
        return None
# ------------------------------------------------


# ----------------- Painel STATUS — MÊS -----------------
def build_month_status_panel(client, situacao=None):
    m_ini, m_fim = month_bounds_today()
    newest = newest_month_key(client, m_ini, m_fim)
    cache_key = (m_ini.isoformat(), m_fim.isoformat(), newest)
    if MONTH_STATUS_CACHE.get('key') == cache_key and MONTH_STATUS_CACHE.get('panel'):
        return MONTH_STATUS_CACHE['panel']

    all_rows, pagina = [], 1
    page_size, page_limit = 100, 12
    for _ in range(page_limit):
        try:
            resp = client.list_sales(to_iso(m_ini), to_iso(m_fim), situacao or None,
                                     pagina=pagina, limite=page_size)
            data = resp.get('data', []) or []
            all_rows.extend(data)
            if len(data) < page_size:
                break
            pagina += 1
        except Exception:
            break

    by_id = {}
    for r in all_rows:
        rid = r.get('id') or r.get('numero')
        if rid is None:
            continue
        if rid not in by_id:
            by_id[rid] = r
    rows = list(by_id.values())

    from collections import defaultdict as dd
    acum = dd(lambda: {'qtd': 0, 'valor': 0.0})
    details = dd(list)

    for r in rows:
        sid = first(r, ['situacao.id', 'idSituacao', 'geral.situacao.id'])
        try:
            sid = int(sid) if sid is not None else None
        except Exception:
            sid = None

        d_raw = first(r, ['dataEmissao', 'data.emissao', 'data'])
        d = parse_date(d_raw)
        if not d or d < m_ini or d > m_fim:
            continue

        valor = parse_total(r.get('total'))
        numero = r.get('numero') or r.get('id')
        data_em_br = br_dmy_short(d_raw)

        acum[sid]['qtd'] += 1
        acum[sid]['valor'] += valor
        details[sid].append({'numero': numero, 'data': data_em_br, 'total': valor})

    # inclui todos os status encontrados
    linhas = []
    tq, tv = 0, 0.0
    for sid, data in acum.items():
        q = int(data['qtd'])
        v = float(data['valor'])
        if q == 0 and v == 0:
            continue
        nome = STATUS_MAP.get(sid, f'STATUS {sid}')
        linhas.append({'sid': sid, 'status': nome, 'qtd': q, 'valor': v})
        tq += q
        tv += v

    linhas.sort(key=lambda x: x['valor'], reverse=True)

    panel = {
        'mes_label': m_ini.strftime('%m/%Y'),
        'status_list': linhas,
        'total_qtd': tq,
        'total_valor': tv,
        'details_by_status': details
    }
    MONTH_STATUS_CACHE['key'] = cache_key
    MONTH_STATUS_CACHE['panel'] = panel
    return panel
# --------------------------------------------------------


# ----------------- Painel VENDEDOR — MÊS (exclui CANCELADO) -----------------
def build_month_vendor_panel(client):
    m_ini, m_fim = month_bounds_today()
    newest = newest_month_key(client, m_ini, m_fim)
    cache_key = (m_ini.isoformat(), m_fim.isoformat(), newest, 'vendor')
    if MONTH_VENDOR_CACHE.get('key') == cache_key and MONTH_VENDOR_CACHE.get('panel'):
        return MONTH_VENDOR_CACHE['panel']

    all_rows, pagina = [], 1
    page_size, page_limit = 100, 12
    for _ in range(page_limit):
        try:
            resp = client.list_sales(to_iso(m_ini), to_iso(m_fim), None, pagina=pagina, limite=page_size)
            data = resp.get('data', []) or []
            all_rows.extend(data)
            if len(data) < page_size:
                break
            pagina += 1
        except Exception:
            break

    by_id = {}
    for r in all_rows:
        rid = r.get('id') or r.get('numero')
        if rid is None:
            continue
        if rid not in by_id:
            by_id[rid] = r
    rows = list(by_id.values())

    from collections import defaultdict as dd
    acum = dd(lambda: {'qtd': 0, 'valor': 0.0})
    details = dd(list)

    detail_cache = {}
    nomes_validos = set(VENDEDOR_MAP.values())
    vendor_has_cancelled = dd(bool)

    for r in rows:
        d_raw = first(r, ['dataEmissao', 'data.emissao', 'data'])
        d = parse_date(d_raw)
        if not d or d < m_ini or d > m_fim:
            continue

        sid = first(r, ['situacao.id', 'idSituacao', 'geral.situacao.id'])
        try:
            sid = int(sid) if sid is not None else None
        except Exception:
            sid = None

        vid = first(r, ['vendedor.id', 'idVendedor', 'geral.vendedor.id'])
        nome_vendor = None

        if vid is None:
            rid = r.get('id') or r.get('numero')
            det = detail_cache.get(rid)
            if det is None:
                try:
                    det = client.get_sale(str(rid)) if rid else None
                except Exception:
                    det = None
                detail_cache[rid] = det
            if det:
                vid = first(det, ['vendedor.id'])
                nome_vendor = first(det, ['vendedor.nome'])

        if vid is not None and nome_vendor is None:
            try:
                nome_vendor = VENDEDOR_MAP.get(int(vid))
            except Exception:
                nome_vendor = None

        vend_key = nome_vendor if (nome_vendor in nomes_validos) else 'SEM VENDEDOR'

        valor = parse_total(r.get('total'))
        numero = r.get('numero') or r.get('id')
        data_em_br = br_dmy_short(d_raw)

        details[vend_key].append({'numero': numero, 'data': data_em_br, 'total': valor, 'sid': sid})
        if sid == 12:
            vendor_has_cancelled[vend_key] = True
        else:
            acum[vend_key]['qtd'] += 1
            acum[vend_key]['valor'] += valor

    linhas = []
    for nome in nomes_validos:
        dct = acum.get(nome)
        if dct:
            linhas.append({
                'vendedor': nome,
                'qtd': int(dct['qtd']),
                'valor': float(dct['valor']),
                'has_cancelled': bool(vendor_has_cancelled[nome])
            })
    if 'SEM VENDEDOR' in acum or vendor_has_cancelled['SEM VENDEDOR']:
        dct = acum.get('SEM VENDEDOR', {'qtd': 0, 'valor': 0.0})
        linhas.append({
            'vendedor': 'SEM VENDEDOR',
            'qtd': int(dct['qtd']),
            'valor': float(dct['valor']),
            'has_cancelled': bool(vendor_has_cancelled['SEM VENDEDOR'])
        })

    linhas.sort(key=lambda x: x['valor'], reverse=True)

    panel = {
        'mes_label': m_ini.strftime('%m/%Y'),
        'vendors_list': linhas,
        'total_qtd': sum(l['qtd'] for l in linhas),
        'total_valor': sum(l['valor'] for l in linhas),
        'details_by_vendor': details
    }
    MONTH_VENDOR_CACHE['key'] = cache_key
    MONTH_VENDOR_CACHE['panel'] = panel
    return panel
# -----------------------------------------------------------------------------


# ----------------- Painel DIAS — MÊS -----------------
def build_month_day_panel(client):
    m_ini, m_fim = month_bounds_today()
    newest = newest_month_key(client, m_ini, m_fim)
    cache_key = (m_ini.isoformat(), m_fim.isoformat(), newest, 'day')

    if MONTH_DAY_CACHE.get('key') == cache_key and MONTH_DAY_CACHE.get('panel'):
        return MONTH_DAY_CACHE['panel']

    status_key = (m_ini.isoformat(), m_fim.isoformat(), newest)
    status_panel = None
    if MONTH_STATUS_CACHE.get('key') == status_key:
        status_panel = MONTH_STATUS_CACHE.get('panel')

    from collections import defaultdict as dd
    acum = dd(lambda: {'qtd': 0, 'valor': 0.0})
    details_by_day = dd(list)
    day_has_cancelled = dd(bool)

    def push_item(d_br, numero, total, sid):
        try:
            d_iso = datetime.strptime(d_br, '%d/%m/%y').date().isoformat()
        except Exception:
            d_iso = d_br
        acum[d_iso]['qtd'] += 1
        acum[d_iso]['valor'] += total
        details_by_day[d_iso].append({'numero': numero, 'data': d_br, 'total': total, 'sid': sid})
        if sid == 12:
            day_has_cancelled[d_iso] = True

    if status_panel and status_panel.get('details_by_status'):
        for sid, lst in (status_panel.get('details_by_status') or {}).items():
            try:
                sid_int = int(sid)
            except Exception:
                sid_int = sid
            for it in lst:
                push_item(it.get('data'), it.get('numero'), parse_total(it.get('total')), sid_int)
    else:
        all_rows, pagina = [], 1
        page_size, page_limit = 100, 12
        for _ in range(page_limit):
            try:
                resp = client.list_sales(to_iso(m_ini), to_iso(m_fim), None,
                                         pagina=pagina, limite=page_size)
                data = resp.get('data', []) or []
                all_rows.extend(data)
                if len(data) < page_size:
                    break
                pagina += 1
            except Exception:
                break
        by_id = {}
        for r in all_rows:
            rid = r.get('id') or r.get('numero')
            if rid is None:
                continue
            if rid not in by_id:
                by_id[rid] = r
        rows = list(by_id.values())

        for r in rows:
            d_raw = first(r, ['dataEmissao', 'data.emissao', 'data'])
            d = parse_date(d_raw)
            if not d or d < m_ini or d > m_fim:
                continue
            sid = first(r, ['situacao.id', 'idSituacao', 'geral.situacao.id'])
            try:
                sid = int(sid) if sid is not None else None
            except Exception:
                sid = None
            push_item(br_dmy_short(d_raw), r.get('numero') or r.get('id'), parse_total(r.get('total')), sid)

    dias = sorted(acum.keys(), reverse=True)
    lines = []
    for k in dias:
        try:
            d_lbl = datetime.strptime(k, '%Y-%m-%d').strftime('%d/%m/%y')
        except Exception:
            d_lbl = k
        lines.append({
            'day_key': k,
            'day_label': d_lbl,
            'qtd': int(acum[k]['qtd']),
            'valor': float(acum[k]['valor']),
            'has_cancelled': bool(day_has_cancelled[k])
        })

    panel = {
        'mes_label': m_ini.strftime('%m/%Y'),
        'days_list': lines,
        'total_qtd': sum(x['qtd'] for x in lines),
        'total_valor': sum(x['valor'] for x in lines),
        'details_by_day': details_by_day
    }
    MONTH_DAY_CACHE['key'] = cache_key
    MONTH_DAY_CACHE['panel'] = panel
    return panel
# -----------------------------------------------------------------------------


# --------- PRODUTOS — HOJE (qtd e valor; ordenação por valor) ----------------
def build_products_today_panel(pedidos):
    """
    Soma QUANTIDADE e VALOR por produto do dia atual.
    - Totais EXCLUEM cancelados (sid==12).
    - Zoom lista todos (cancelado em vermelho).
    - Ordena por maior VALOR total.
    """
    hoje = br_now_saopaulo().strftime('%d/%m/%y')
    prods = defaultdict(lambda: {'qtd': 0.0, 'valor': 0.0, 'has_cancelled': False, 'details': []})

    for p in pedidos:
        if p.get('_data_emissao_br') != hoje:
            continue
        sid = p.get('_situacao_id')
        pid = p.get('_numero') or p.get('numero') or p.get('id')
        data_br = p.get('_data_emissao_br') or '-'
        itens = p.get('itens_norm') or []
        for it in itens:
            key = (it.get('_nome') or '-', it.get('_sku') or '-')
            q = parse_qty(it.get('_qtd') or 0)
            v_item = (it.get('_preco') or 0.0) * q
            prods[key]['details'].append({
                'numero': pid,
                'data': data_br,
                'qtd': q,
                'valor': v_item,
                'sid': sid
            })
            if sid == 12:
                prods[key]['has_cancelled'] = True
            else:
                prods[key]['qtd'] += q
                prods[key]['valor'] += v_item

    lines, total_qtd, total_valor = [], 0.0, 0.0
    for (nome, sku), d in prods.items():
        lines.append({
            'produto': nome,
            'sku': sku,
            'qtd': d['qtd'],
            'valor': d['valor'],
            'has_cancelled': d['has_cancelled'],
            'detail_id': f"pd-{abs(hash((nome, sku))) % 10**8}",
        })
        total_qtd += d['qtd']
        total_valor += d['valor']

    lines.sort(key=lambda x: x['valor'], reverse=True)

    details_map = {}
    for (nome, sku), d in prods.items():
        details_map[(nome, sku)] = d['details']

    panel = {
        'day_label': hoje,
        'products_list': lines,
        'total_qtd': total_qtd,
        'total_valor': total_valor,
        'details_by_product': details_map
    }
    return panel
# -----------------------------------------------------------------------------


# --------- PRODUTOS — MÊS (qtd e valor; ordenação por valor) -----------------
def build_products_month_panel(client):
    """
    Soma QUANTIDADE e VALOR por produto no mês atual.
    - Totais EXCLUEM cancelados (sid==12).
    - Zoom lista todos (cancelado em vermelho).
    - Ordena por maior VALOR total.
    """
    m_ini, m_fim = month_bounds_today()
    newest = newest_month_key(client, m_ini, m_fim)
    cache_key = (m_ini.isoformat(), m_fim.isoformat(), newest, 'prod-month')
    if MONTH_PROD_CACHE.get('key') == cache_key and MONTH_PROD_CACHE.get('panel'):
        return MONTH_PROD_CACHE['panel']

    all_rows, pagina = [], 1
    page_size, page_limit = 100, 20
    for _ in range(page_limit):
        try:
            resp = client.list_sales(to_iso(m_ini), to_iso(m_fim), None, pagina=pagina, limite=page_size)
            data = resp.get('data', []) or []
            all_rows.extend(data)
            if len(data) < page_size:
                break
            pagina += 1
        except Exception:
            break

    by_id = {}
    for r in all_rows:
        rid = r.get('id') or r.get('numero')
        if rid is None:
            continue
        if rid not in by_id:
            by_id[rid] = r
    rows = list(by_id.values())

    prods = defaultdict(lambda: {'qtd': 0.0, 'valor': 0.0, 'has_cancelled': False, 'details': []})
    detail_cache = {}

    for r in rows:
        d_raw = first(r, ['dataEmissao', 'data.emissao', 'data'])
        d = parse_date(d_raw)
        if not d or d < m_ini or d > m_fim:
            continue

        sid = first(r, ['situacao.id', 'idSituacao', 'geral.situacao.id'])
        try:
            sid = int(sid) if sid is not None else None
        except Exception:
            sid = None

        pid = r.get('numero') or r.get('id')
        data_br = br_dmy_short(d_raw)

        itens = r.get('itens')
        if not itens:
            det = detail_cache.get(pid)
            if det is None:
                try:
                    det = client.get_sale(str(pid)) if pid else None
                except Exception:
                    det = None
                detail_cache[pid] = det
            itens = (det or {}).get('itens') or []

        for i in itens:
            ni = normalize_item(i)
            key = (ni['_nome'] or '-', ni['_sku'] or '-')
            q = parse_qty(ni['_qtd'])
            v_item = (ni['_preco'] or 0.0) * q
            prods[key]['details'].append({
                'numero': pid,
                'data': data_br,
                'qtd': q,
                'valor': v_item,
                'sid': sid
            })
            if sid == 12:
                prods[key]['has_cancelled'] = True
            else:
                prods[key]['qtd'] += q
                prods[key]['valor'] += v_item

    lines, total_qtd, total_valor = [], 0.0, 0.0
    for (nome, sku), d in prods.items():
        lines.append({
            'produto': nome,
            'sku': d['sku'] if isinstance(d, dict) and 'sku' in d else sku,
            'qtd': d['qtd'],
            'valor': d['valor'],
            'has_cancelled': d['has_cancelled'],
            'detail_id': f"pm-{abs(hash((nome, sku))) % 10**8}",
        })
        total_qtd += d['qtd']
        total_valor += d['valor']

    lines.sort(key=lambda x: x['valor'], reverse=True)

    details_map = {}
    for (nome, sku), d in prods.items():
        details_map[(nome, sku)] = d['details']

    panel = {
        'mes_label': m_ini.strftime('%m/%Y'),
        'products_list': lines,
        'total_qtd': total_qtd,
        'total_valor': total_valor,
        'details_by_product': details_map
    }
    MONTH_PROD_CACHE['key'] = cache_key
    MONTH_PROD_CACHE['panel'] = panel
    return panel
# -----------------------------------------------------------------------------


# =================== ROTA PRINCIPAL ===================
@app.route('/')
def index():
    if not session.get('bling_token'):
        return render_template('login.html', conectado=False)

    situacao = request.args.get('situacao', '').strip()
    di = request.args.get('data_ini', '')
    df = request.args.get('data_fim', '')

    # sort de produtos (dia/mês)
    psd = request.args.get('psd', 'valor')  # produtos dia
    psm = request.args.get('psm', 'valor')  # produtos mês

    # flag para buscar análise na planilha
    buscar_analise = request.args.get('buscar_analise') == '1'

    if not di or not df:
        d_ini, d_fim = default_dates()
    else:
        try:
            d_ini = datetime.strptime(di, '%Y-%m-%d').date()
            d_fim = datetime.strptime(df, '%Y-%m-%d').date()
        except ValueError:
            d_ini, d_fim = default_dates()

    client = api()
    if not client.session.get('bling_token'):
        flash('Conecte ao Bling para continuar.', 'warning')
        return redirect(url_for('login'))

    # Assinaturas para invalidação
    m_ini, m_fim = month_bounds_today()
    force = request.args.get('refresh') == 'force'
    month_newest = None if force else newest_month_key(client, m_ini, m_fim)
    daily_newest = None if force else newest_range_key(client, d_ini, d_fim)

    snapshot_key = (
        m_ini.isoformat(),
        m_fim.isoformat(),
        month_newest,
        'daily',
        daily_newest,
        psd,
        psm,
        buscar_analise,
    )

    if (not force) and PAGE_SNAPSHOT.get('key') == snapshot_key and PAGE_SNAPSHOT.get('context'):
        ctx = PAGE_SNAPSHOT['context']
    else:
        pedidos = []
        try:
            resp = client.list_sales(to_iso(d_ini), to_iso(d_fim), situacao or None, pagina=1, limite=50)
            pedidos = resp.get('data', [])
        except Exception as e:
            flash(f'Erro ao buscar pedidos: {e}', 'danger')

        enriched = []
        for p in pedidos:
            pid = p.get('id') or p.get('numero')
            det = None
            try:
                if pid:
                    det = client.get_sale(str(pid))
            except Exception:
                det = None

            itens = (det or {}).get('itens') or p.get('itens') or []
            p['itens_norm'] = [normalize_item(i) for i in itens]
            p['_numero'] = p.get('numero') or p.get('id')

            vendedor_id = (det or {}).get('vendedor', {}).get('id') or first(
                p, ['vendedor.id', 'idVendedor', 'geral.vendedor.id']
            )
            nome_vendedor = None
            try:
                if vendedor_id is not None:
                    nome_vendedor = VENDEDOR_MAP.get(int(vendedor_id))
            except Exception:
                nome_vendedor = None
            p['_vendedor_display'] = nome_vendedor or (str(vendedor_id) if vendedor_id else '-')

            situacao_id = first(p, ['situacao.id', 'idSituacao', 'geral.situacao.id'])
            try:
                sid = int(situacao_id) if situacao_id is not None else None
            except Exception:
                sid = None
            p['_situacao_id'] = sid
            p['_situacao_display'] = STATUS_MAP.get(sid, str(situacao_id) if situacao_id else '-')

            data_em = first(p, ['dataEmissao', 'data.emissao', 'data'])
            p['_data_emissao_br'] = br_dmy_short(data_em)

            p['_obs'] = first(det or p, ['observacoes', 'obs']) or ''
            p['_obs_int'] = first(det or p, ['observacoesInternas']) or ''

            pars = (det or {}).get('parcelas') or p.get('parcelas') or []
            norm = []
            for par in pars:
                fpid = None
                if isinstance(par.get('formaPagamento'), dict):
                    fpid = par['formaPagamento'].get('id')
                desc = None
                norm.append({
                    'id': par.get('id'),
                    'dataVencimento': br_dmy_short(par.get('dataVencimento') or par.get('vencimento')),
                    'valor': par.get('valor') or 0,
                    'observacoes': par.get('observacoes') or '',
                    'caut': par.get('caut') or '',
                    'formaPagamentoId': fpid,
                    'formaPagamentoDesc': desc or (str(fpid) if fpid is not None else None)
                })
            p['_parcelas'] = norm

            frete_raw = first(det or p, ['transporte.frete', 'frete'])
            p['_frete'] = parse_total(frete_raw)

            p['_raw_pair'] = {'lista': {k: v for k, v in p.items() if not str(k).startswith('_')},
                              'detalhes': det}
            enriched.append(p)

        # === Buscar análise de margem na planilha, se solicitado ===
        if buscar_analise and enriched:
            sheet_url = get_analysis_sheet_url()
            if not sheet_url:
                flash('Cadastre primeiro a URL da planilha de análise de vendas em "Configurações".', 'warning')
            else:
                try:
                    margin_map = load_margin_map_from_sheet(sheet_url)
                    for p in enriched:
                        num = str(p.get('_numero') or p.get('numero') or p.get('id') or '').strip()
                        if num and num in margin_map:
                            p['_margem_lucro'] = margin_map[num]
                except Exception as e:
                    flash(f'Erro ao buscar análise na planilha: {e}', 'danger')

        session['last_raw_json'] = json.dumps(enriched[-1]['_raw_pair'], ensure_ascii=False) if enriched else None

        vendor_panels, totais = build_daily_panels(enriched)
        month_status_panel = build_month_status_panel(client, situacao=None)
        month_vendor_panel = build_month_vendor_panel(client)
        month_day_panel = build_month_day_panel(client)

        # ====== DADOS DO GRÁFICO (VENDAS DIÁRIAS DO MÊS) ======
        dias_list = month_day_panel['days_list']
        dias_list_graf = list(reversed(dias_list))
        graf_labels = [d['day_label'] for d in dias_list_graf]
        graf_values = [d['valor'] for d in dias_list_graf]
        graf_labels_json = json.dumps(graf_labels, ensure_ascii=False)
        graf_values_json = json.dumps(graf_values, ensure_ascii=False)
        # =====================================================

        # Painéis de produtos
        prod_day_panel = build_products_today_panel(enriched)
        prod_month_panel = build_products_month_panel(client)

        # aplica ordenação escolhida
        if psd == 'qtd':
            prod_day_panel['products_list'].sort(key=lambda x: x['qtd'], reverse=True)
        else:
            prod_day_panel['products_list'].sort(key=lambda x: x['valor'], reverse=True)

        if psm == 'qtd':
            prod_month_panel['products_list'].sort(key=lambda x: x['qtd'], reverse=True)
        else:
            prod_month_panel['products_list'].sort(key=lambda x: x['valor'], reverse=True)

        # URLs de toggle ↑↓ e Buscar Análise
        args_dict = request.args.to_dict()
        # produtos dia
        new_psd = 'qtd' if psd == 'valor' else 'valor'
        args_psd = dict(args_dict, psd=new_psd)
        toggle_psd_url = url_for('index', **args_psd)
        # produtos mês
        new_psm = 'qtd' if psm == 'valor' else 'valor'
        args_psm = dict(args_dict, psm=new_psm)
        toggle_psm_url = url_for('index', **args_psm)
        # buscar análise
        args_busca = dict(args_dict, buscar_analise='1')
        buscar_analise_url = url_for('index', **args_busca)

        ctx = {
            'pedidos': enriched,
            'vendor_panels': vendor_panels,
            'totais': totais,
            'periodo': {'ini': d_ini.strftime('%d/%m/%y'), 'fim': d_fim.strftime('%d/%m/%y')},
            'month_status_panel': month_status_panel,
            'month_vendor_panel': month_vendor_panel,
            'month_day_panel': month_day_panel,
            'prod_day_panel': prod_day_panel,
            'prod_month_panel': prod_month_panel,
            'last_updated': fmt_br_min(br_now_saopaulo()),
            'graf_labels_json': graf_labels_json,
            'graf_values_json': graf_values_json,
            'psd': psd,
            'psm': psm,
            'toggle_psd_url': toggle_psd_url,
            'toggle_psm_url': toggle_psm_url,
            'buscar_analise_url': buscar_analise_url,
            'buscar_analise': buscar_analise,
        }

        PAGE_SNAPSHOT['key'] = snapshot_key
        PAGE_SNAPSHOT['context'] = ctx
        PAGE_SNAPSHOT['at'] = br_now_saopaulo()

    # render com ctx (seja cache ou novo)
    return render_template(
        'index.html',
        conectado=True,
        pedidos=ctx['pedidos'],
        vendor_panels=ctx['vendor_panels'],
        totais=ctx['totais'],
        periodo=ctx['periodo'],
        month_status_panel=ctx['month_status_panel'],
        month_vendor_panel=ctx['month_vendor_panel'],
        month_day_panel=ctx['month_day_panel'],
        prod_day_panel=ctx['prod_day_panel'],
        prod_month_panel=ctx['prod_month_panel'],
        filtros={
            'situacao': request.args.get('situacao', ''),
            'data_ini': request.args.get('data_ini', ''),
            'data_fim': request.args.get('data_fim', '')
        },
        last_updated=ctx['last_updated'],
        graf_labels_json=ctx.get('graf_labels_json', '[]'),
        graf_values_json=ctx.get('graf_values_json', '[]'),
        psd=ctx.get('psd', 'valor'),
        psm=ctx.get('psm', 'valor'),
        toggle_psd_url=ctx.get('toggle_psd_url', url_for('index')),
        toggle_psm_url=ctx.get('toggle_psm_url', url_for('index')),
        buscar_analise_url=ctx.get('buscar_analise_url', url_for('index')),
        buscar_analise=ctx.get('buscar_analise', False),
    )


# ======== CONFIGURAÇÕES (URL PLANILHA) ========
@app.route('/config', methods=['GET', 'POST'])
def config_view():
    if not session.get('bling_token'):
        return redirect(url_for('index'))

    current_url = get_analysis_sheet_url() or ''

    if request.method == 'POST':
        new_url = request.form.get('analysis_sheet_url', '').strip()
        if not new_url:
            flash('Informe a URL da planilha de análise de vendas.', 'warning')
        else:
            try:
                save_sheet_config(new_url)
                flash('URL da planilha de análise salva com sucesso!', 'success')
                return redirect(url_for('config_view'))
            except Exception as e:
                flash(f'Erro ao salvar a URL: {e}', 'danger')

    return render_template(
        'config.html',
        conectado=True,
        analysis_sheet_url=current_url
    )


# ======== AUXILIARES UI ========
@app.route('/api-fields')
def api_fields():
    raw = session.get('last_raw_json')
    if not raw:
        flash('Nenhum pedido carregado ainda.', 'warning')
        return redirect(url_for('index'))
    try:
        pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except Exception:
        pretty = raw
    return render_template('api_fields.html', pretty=pretty, conectado=True)


@app.route('/login')
def login():
    return redirect(api().auth_url())


@app.route('/callback')
def callback():
    err = request.args.get('error')
    if err:
        flash(f'Erro OAuth: {err}', 'danger')
        return redirect(url_for('index'))
    code = request.args.get('code')
    if not code:
        flash('Código ausente.', 'danger')
        return redirect(url_for('index'))
    try:
        api().exchange_code(code)
        flash('Conectado ao Bling com sucesso!', 'success')
    except Exception as e:
        flash(f'Falha ao trocar código por token: {e}', 'danger')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada.', 'info')
    return redirect(url_for('index'))


# =================== MAIN ===================
if __name__ == '__main__':
    try:
        port = int(getattr(settings, 'PORT', 5050) or 5050)
    except Exception:
        port = 5050
    print(f'ABLING V25t - porta {port}')
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)

from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Flask, render_template, redirect, request, session, url_for, flash
from config import settings
from bling import BlingAPI
import json
from collections import defaultdict

app = Flask(__name__)
app.secret_key = settings.FLASK_SECRET_KEY

# Mapeamentos já usados no sistema
STATUS_MAP = {
    56035: 'AGUARDANDO SEPARAÇÃO',
    6: 'EM ABERTO',
    466202: 'ENVIO ESTOQUE FULL',
    12: 'CANCELADO',
    9: 'ATENDIDO',
    67578: 'ENTREGUE',
    446927: 'SEPARADO AGUARDANDO COLETA',
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

def default_dates():
    try:
        tz = ZoneInfo('America/Sao_Paulo')
        today = datetime.now(tz).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()
    # últimos 3 dias (inclusive hoje)
    return today - timedelta(days=2), today

def to_iso(d):
    if isinstance(d, datetime):
        d = d.date()
    return d.isoformat()

def first(d, keys):
    """Busca a primeira chave existente (inclusive aninhada com '.')"""
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
    """Formata data para dd/mm/yy"""
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

def brl(v):
    """Formata número como BRL: R$ 1.234,56"""
    try:
        v = float(v or 0)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")

def parse_total(raw) -> float:
    """Converte valores que podem vir como float (8086.44) ou string BRL ('R$ 14.487,48')."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace('R$', '').replace(' ', '')
    # Se tem vírgula, tratamos como BR: remove milhares '.' e troca ',' por '.'
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def normalize_item(i):
    prod = i.get('produto') or {}
    nome = prod.get('nome') or i.get('descricao') or '-'
    sku = prod.get('codigo') or i.get('codigo') or '-'
    qtd = i.get('quantidade') or 0
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
    return BlingAPI(settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET, settings.BLING_REDIRECT_URI, session)

@app.template_filter('brl')
def jinja_brl(v):
    return brl(v)

@app.route('/')
def index():
    if not session.get('bling_token'):
        return render_template('login.html', conectado=False)

    situacao = request.args.get('situacao', '').strip()
    di = request.args.get('data_ini', '')
    df = request.args.get('data_fim', '')
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

        vendedor_id = (det or {}).get('vendedor', {}).get('id') or first(p, ['vendedor.id', 'idVendedor', 'geral.vendedor.id'])
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
        p['_situacao_display'] = STATUS_MAP.get(sid, str(situacao_id) if situacao_id else '-')

        data_em = first(p, ['dataEmissao', 'data.emissao', 'data'])
        p['_data_emissao_br'] = br_dmy_short(data_em)

        # Observações
        p['_obs'] = first(det or p, ['observacoes', 'obs']) or ''
        p['_obs_int'] = first(det or p, ['observacoesInternas']) or ''

        # Parcelas
        pars = (det or {}).get('parcelas') or p.get('parcelas') or []
        norm = []
        for par in pars:
            fpid = None
            if isinstance(par.get('formaPagamento'), dict):
                fpid = par['formaPagamento'].get('id')
            desc = None
            try:
                if fpid is not None:
                    desc = FORMAPAG_MAP.get(int(fpid))
            except Exception:
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

        # >>> FRETE (transporte.frete)
        frete_raw = first(det or p, ['transporte.frete', 'frete'])
        p['_frete'] = parse_total(frete_raw)

        p['_raw_pair'] = {'lista': {k: v for k, v in p.items() if not str(k).startswith('_')}, 'detalhes': det}
        enriched.append(p)

    session['last_raw_json'] = json.dumps(enriched[-1]['_raw_pair'], ensure_ascii=False) if enriched else None

    # ===== Painéis (3 dias): somatório por VENDEDOR usando o CAMPO TOTAL =====
    por_dia_vend = defaultdict(lambda: defaultdict(lambda: {'qtd': 0, 'valor': 0.0}))
    vendedores_fixos = ['MERCADO LIVRE', 'WENIO', 'JOICE', 'RANGEL']

    for p in enriched:
        dia_br = p.get('_data_emissao_br')  # dd/mm/yy
        if not dia_br or dia_br == '-':
            continue
        try:
            dia_key = datetime.strptime(dia_br, '%d/%m/%y').date()
        except Exception:
            continue

        vend = (p.get('_vendedor_display') or '-').upper().strip()
        if vend not in vendedores_fixos:
            continue

        # Total do pedido (pode vir float ou string BRL)
        raw_total = p.get('total')
        if raw_total is None:
            raw_total = (p.get('_raw_pair') or {}).get('detalhes', {}).get('total')
        valor = parse_total(raw_total)

        por_dia_vend[dia_key][vend]['qtd'] += 1
        por_dia_vend[dia_key][vend]['valor'] += valor

    dias_ordenados = sorted(list(por_dia_vend.keys()), reverse=True)[:3]

    vendor_panels = []
    for d in dias_ordenados:
        # monta vendedores e calcula TOTAL DO DIA
        vendedores_list = []
        total_qtd_dia = 0
        total_valor_dia = 0.0
        for v in vendedores_fixos:
            dados = por_dia_vend[d][v]  # defaultdict garante existência
            q = int(dados['qtd'])
            val = float(dados['valor'])
            vendedores_list.append({'nome': v, 'qtd': q, 'valor': val})
            total_qtd_dia += q
            total_valor_dia += val

        vendor_panels.append({
            'dia_label': d.strftime('%d/%m/%y'),
            'vendedores': vendedores_list,
            'total_qtd': total_qtd_dia,
            'total_valor': total_valor_dia
        })

    # ===== KPI do topo passa a ser a SOMA dos painéis (mesma lógica do Bling) =====
    kpi_qtd = sum(d['total_qtd'] for d in vendor_panels)
    kpi_valor = sum(d['total_valor'] for d in vendor_panels)
    totais = {'qtd_pedidos': kpi_qtd, 'valor_produtos': kpi_valor}

    return render_template(
        'index.html',
        pedidos=enriched,
        filtros={'situacao': situacao, 'data_ini': d_ini.isoformat(), 'data_fim': d_fim.isoformat()},
        periodo={'ini': d_ini.strftime('%d/%m/%y'), 'fim': d_fim.strftime('%d/%m/%y')},
        totais=totais,
        conectado=True,
        vendor_panels=vendor_panels
    )

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

if __name__ == '__main__':
    print('ABLING V25t - porta', settings.PORT)
    app.run(host='0.0.0.0', port=settings.PORT, debug=True)

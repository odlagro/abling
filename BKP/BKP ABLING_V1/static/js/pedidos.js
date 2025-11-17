(async function () {
  const tbody = document.getElementById('tbody-pedidos');
  const btnRefresh = document.getElementById('btn-refresh');
  const lastRefresh = document.getElementById('last-refresh');
  const statusFilter = document.getElementById('status-filter');
  const alertArea = document.getElementById('alert-area');

  let lastDataHash = null;
  let timer = null;

  function fmtBRL(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
    try { return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); }
    catch { return String(v); }
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      const y = d.getFullYear();
      const m = String(d.getMonth()+1).padStart(2,'0');
      const day = String(d.getDate()).padStart(2,'0');
      return `${y}-${m}-${day}`;
    } catch { return iso; }
  }

  function rowPedido(p) {
    const id = `p-${p.numero}`;
    const vendedor = p.vendedor_nome || p.vendedor || 'Sem nome';
    const status = p.status_nome || p.status || '—';
    const total = Number(p.total ?? 0);
    const data = p.data || p.createdAt || p.dataEmissao || p.data_pedido;

    const itens = (p.itens || []).map((it, idx) => {
      const nome = it.nome || it.descricao || it.titulo || `Item ${idx+1}`;
      const q = Number(it.quantidade ?? it.qtde ?? 1);
      const preco = Number(it.preco ?? it.valor ?? it.vlr ?? 0);
      const subtotal = q * preco;
      const sku = it.sku || it.codigo || '';
      return `
        <tr>
          <td class="text-muted">${sku}</td>
          <td>${nome}</td>
          <td class="text-end">${q}</td>
          <td class="text-end">${fmtBRL(preco)}</td>
          <td class="text-end">${fmtBRL(subtotal)}</td>
        </tr>`;
    }).join('') || `<tr><td colspan="5" class="text-center text-muted">Sem itens</td></tr>`;

    const itemTable = `
      <div class="order-items" id="${id}-items" data-visible="1">
        <div class="table-responsive">
          <table class="table table-sm table-dark table-striped mb-2">
            <thead>
              <tr>
                <th style="width:120px">SKU</th>
                <th>Produto</th>
                <th class="text-end" style="width:100px">Qtde</th>
                <th class="text-end" style="width:120px">Preço</th>
                <th class="text-end" style="width:140px">Subtotal</th>
              </tr>
            </thead>
            <tbody>${itens}</tbody>
          </table>
        </div>
      </div>`;

    const tr = document.createElement('tr');
    tr.className = 'pedido-row';
    tr.innerHTML = `
      <td>${p.numero}</td>
      <td>${fmtDate(data)}</td>
      <td>${p.cliente_nome || p.cliente || p.contato || '—'}</td>
      <td>${vendedor}</td>
      <td><span class="status-dot"></span><span>${status}</span></td>
      <td class="fw-semibold">${fmtBRL(total)}</td>
      <td><button class="btn btn-sm btn-outline-light" data-action="toggle" data-target="${id}-items">Ocultar</button></td>`;

    const details = document.createElement('tr');
    details.className = 'pedido-details';
    const td = document.createElement('td');
    td.colSpan = 7;
    td.innerHTML = itemTable;
    details.appendChild(td);
    return [tr, details];
  }

  function render(pedidos, statuses, active) {
    // Dropdown
    const current = statusFilter.value || 'Em aberto';
    statusFilter.innerHTML = '';
    (statuses && statuses.length ? statuses : ['Em aberto']).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      statusFilter.appendChild(opt);
    });
    statusFilter.value = (statuses || []).includes(active) ? active : (current || 'Em aberto');

    // Rows
    tbody.innerHTML = '';
    if (!pedidos || pedidos.length === 0) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="7" class="text-center text-muted py-4">Nenhum pedido encontrado</td>`;
      tbody.appendChild(tr);
    } else {
      const frag = document.createDocumentFragment();
      pedidos.forEach(p => { const [r, d] = rowPedido(p); frag.appendChild(r); frag.appendChild(d); });
      tbody.appendChild(frag);
      tbody.querySelectorAll('button[data-action="toggle"]').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-target');
          const wrap = document.getElementById(id);
          const visible = wrap.getAttribute('data-visible') === '1';
          wrap.style.display = visible ? 'none' : '';
          wrap.setAttribute('data-visible', visible ? '0' : '1');
          btn.textContent = visible ? 'Mostrar' : 'Ocultar';
        });
      });
    }
    lastRefresh.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');
  }

  function hashData(obj) {
    try { return btoa(unescape(encodeURIComponent(JSON.stringify(obj)))).slice(0,128); }
    catch { return String(Math.random()); }
  }

  async function fetchPedidos(silent=false) {
    try {
      if (!silent) lastRefresh.textContent = 'Atualizando…';
      const status = encodeURIComponent(statusFilter.value || 'Em aberto');
      const res = await fetch(`/api/pedidos?status=${status}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const lista = data.pedidos || [];
      const newHash = hashData(lista.map(p => ({ numero: p.numero, updatedAt: p.updatedAt || p.data })));
      if (newHash !== lastDataHash) { render(lista, data.statuses, data.active_status); lastDataHash = newHash; }
      else if (!silent) { lastRefresh.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR'); }
    } catch (err) {
      console.error('fetchPedidos error:', err);
      showAlert('danger', 'Erro ao buscar pedidos. ' + (err?.message || ''));
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">Falha ao carregar pedidos</td></tr>`;
    }
  }

  function showAlert(type, msg) {
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show`;
    div.role = 'alert';
    div.innerHTML = `${msg}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    alertArea.appendChild(div);
  }

  btnRefresh?.addEventListener('click', () => fetchPedidos());
  statusFilter?.addEventListener('change', () => fetchPedidos());

  let timer=null;
  function startTimer(){ if (timer) clearInterval(timer); timer = setInterval(() => fetchPedidos(true), 20000); }
  function stopTimer(){ if (timer) clearInterval(timer); timer = null; }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') { startTimer(); fetchPedidos(true); }
    else { stopTimer(); }
  });

  // Initial selection MUST be "Em aberto"
  statusFilter.value = 'Em aberto';
  await fetchPedidos();
  startTimer();
})();
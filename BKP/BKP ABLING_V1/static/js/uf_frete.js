// static/js/uf_frete.js
(function () {
  const selId = "ufSelect";
  const freteId = "frete";
  const msgId = "ufFreteMsg";

  function setMsg(t) {
    const el = document.getElementById(msgId);
    if (el) el.textContent = t || "";
  }

  async function loadUFs() {
    const sel = document.getElementById(selId);
    if (!sel) return;
    try {
      setMsg("Carregando UFs...");
      const r = await fetch("/api/ufs", { cache: "no-store" });
      const data = await r.json();
      if (!data.ok) throw new Error("Falha ao carregar UFs");
      sel.innerHTML = '<option value="">UF...</option>' + data.ufs.map(u => `<option value="${u}">${u}</option>`).join("");
      setMsg("");
    } catch (e) {
      setMsg("Não foi possível carregar UFs agora.");
    }
  }

  async function onUFChange(uf) {
    const freteInput = document.getElementById(freteId);
    if (!freteInput || !uf) return;
    try {
      setMsg("Buscando frete...");
      const r = await fetch(`/api/frete?uf=${encodeURIComponent(uf)}`, { cache: "no-store" });
      const data = await r.json();
      if (!data.ok) {
        setMsg(data.error || "Erro ao buscar frete.");
        return;
      }
      const val = (data.frete ?? 0);
      const formatted = val.toFixed(2).replace(".", ",");
      freteInput.value = formatted;
      freteInput.dispatchEvent(new Event("input", { bubbles: true }));
      freteInput.dispatchEvent(new Event("change", { bubbles: true }));
      setMsg(`Frete de ${data.uf} aplicado.`);
    } catch (e) {
      setMsg("Falha de rede ao consultar frete.");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const sel = document.getElementById(selId);
    if (!sel) return;
    loadUFs();
    sel.addEventListener("change", (ev) => {
      const uf = ev.target.value;
      if (uf) onUFChange(uf);
    });
  });
})();

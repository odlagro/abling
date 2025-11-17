# Patch "UF → Frete" para ApoioV

Este patch **não altera** suas funcionalidades atuais: apenas adiciona um seletor de **UF** e preenche o campo **Frete (R$)** automaticamente lendo a guia **FRETE** da sua planilha.

## Arquivos incluídos
- `frete_blueprint.py` — Blueprint Flask com as rotas:
  - `GET /api/ufs` — lista de UFs
  - `GET /api/frete?uf=XX` — valor do frete para a UF
- `static/js/uf_frete.js` — JavaScript para popular UFs e preencher o campo `#frete`
- `templates/partials/uf_frete.html` — snippet HTML do seletor UF (inserir perto do campo Frete)
- `.env.example_patch` — variáveis opcionais

## Como integrar

1) **Copie os arquivos** para dentro do seu ApoioV:
```
/seu_apoiov/
  frete_blueprint.py
  static/js/uf_frete.js
  templates/partials/uf_frete.html
```
Crie as pastas se não existirem.

2) **Registre o blueprint** no seu `app.py` (ou onde cria o Flask app):
```python
from frete_blueprint import frete_bp
app.register_blueprint(frete_bp)  # adiciona /api/ufs e /api/frete
```

3) **Inclua o seletor de UF no HTML** onde fica o campo **Frete (R$)**.
- Garanta que o **input do Frete** tenha `id="frete"` (ex.: `<input id="frete" ...>`).
- Insira o partial no ponto desejado (acima ou ao lado do frete):
```html
{% include 'partials/uf_frete.html' %}
```
- No final do HTML (antes de `</body>`), **importe o script**:
```html
<script src="{{ url_for('static', filename='js/uf_frete.js') }}"></script>
```

4) **Variáveis de ambiente (opcional)** — adicione ao seu `.env`:
```
FRETE_SHEET_ID=1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg
FRETE_GID=117017797
FRETE_CACHE_TTL=1800
```
> Por padrão já usa os valores acima. Ajuste se sua planilha mudar.

5) **Instale dependências** (se ainda não tiver `requests`):
```
pip install requests
```

6) **Reinicie** o ApoioV. Ao abrir a página, escolha a **UF** e o sistema preencherá o **Frete (R$)**. O script dispara eventos `input`/`change` no campo para acionar seus cálculos existentes.

## Como funciona
- Lemos o CSV público da aba **FRETE** via:
  `https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={FRETE_GID}`
- Cache simples em memória evita atrasos (30 min por padrão).
- O front-end preenche `#frete` com formato `12,34` e dispara eventos para atualizar totais/parcelas que você já tem.

## Dicas
- Se o seu campo de frete tiver outro `id`, troque a constante `freteId` no `static/js/uf_frete.js`.
- Se a planilha usar outras legendas de coluna, o blueprint tenta detectar automaticamente,
  mas o ideal é manter colunas **UF** e **FRETE**.
- Render.com precisa de saída de rede liberada (default é liberado).

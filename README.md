# ABLING-V25t_full — Pill Fix

Este pacote inclui a **correção da pílula amarela** exibindo o **número do pedido** vindo da API (`pedido.numero`, com fallback para `pedido.id`).

## O que mudou
1. Template `templates/index.html` passou a renderizar `#{{ pedido.numero or pedido.id }}` dentro de uma pílula amarela.
2. Adicionado estilo `.badge` e `.badge-yellow` em `static/css/style.css`.

> Se você possui um template mais completo, copie **apenas** o trecho abaixo para onde exibe o número do pedido:

```html
<span class="badge badge-yellow">#{{ pedido.numero or pedido.id }}</span>
```

## Importante
- O backend precisa garantir que o objeto enviado ao template contenha `numero` (ou `id`), por exemplo:

```python
pedido_view = {
    "numero": pedido.get("numero") or pedido.get("id"),
    # demais campos...
}
```

## Executando
```bash
pip install -r requirements.txt  # se aplicável
python app.py
```

Se precisar, posso fundir esta alteração no seu template atual fielmente (mande o HTML atual do card do pedido).

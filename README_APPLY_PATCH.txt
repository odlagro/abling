ABLING V25t — PATCH UI (pílula amarela + itens do pedido) — 2025-11-03 14:59

Arquivos:
- templates/partials/pedidos_list.html
- static/css/pedidos_patch.css
- static/js/pedidos_toggle.js

Como aplicar rapidamente:
1) Copie o HTML para templates/partials/ do projeto.
   No arquivo da listagem de pedidos, insira:
   {% include 'partials/pedidos_list.html' %}
2) Adicione no <head>:
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pedidos_patch.css') }}">
3) Antes do </body>:
   <script src="{{ url_for('static', filename='js/pedidos_toggle.js') }}"></script>

Certifique-se que os filtros Jinja existem:
- 'brl' para moeda BRL
- 'date_br' para dd/mm/aa

Estrutura esperada do objeto 'p':
- numero, data, situacao_desc/situacao, vendedor_nome, total
- itens: [{'descricao','sku','quantidade','preco'}]
- parcelas (opcional): [{'dataVencimento','valor','observacoes','formaPagamento_nome/formaPagamento_id'}]

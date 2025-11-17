# ABLING-V1 (baseline estável)
- Últimos 3 dias por padrão (todas as situações) com filtro de Situação no topo.
- Data do pedido no formato **DD/MM/AA**.
- Vendedor: mostra **nome** quando disponível; caso contrário mostra **idVendedor <ID>**.
- Tema dark, itens visíveis, auto refresh 3 min.

## Rodar
1) Copie `.env.example` para `.env` e preencha as variáveis de OAuth do Bling.
2) `pip install -r requirements.txt`
3) `python app.py` e acesse `http://127.0.0.1:5050/`

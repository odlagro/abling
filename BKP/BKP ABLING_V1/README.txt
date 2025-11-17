
# Pedidos Bling – Flask (tema escuro) – v3

Correção: uso de **HTTP Basic** no endpoint `/oauth/token` (resolve `invalid_client: Client credentials were not found in the headers`).  
Inclui rota `/debug_env` para conferir se o `.env` foi carregado.

## Como usar
1. `.env` a partir de `.env.example` com BLING_CLIENT_ID/SECRET e BLING_REDIRECT_URI (mesmo da configuração do App).
2. `pip install -r requirements.txt` e `python app.py`
3. Acesse `http://127.0.0.1:5050` → **Reconectar** para autorizar.
4. Se aparecer **403 insufficient_scope**, habilite no App os escopos:
   - **Pedido de venda (order)**
   - **Situações – Módulos**
   e reconecte.

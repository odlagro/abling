ABLING-V25t_full (restaurado) - instruções rápidas

1) pip install flask python-dotenv requests
2) Crie .env na raiz com:
FLASK_SECRET=dev-secret
PORT=5050
BLING_CLIENT_ID=SEU_CLIENT_ID_EMPRESA1
BLING_CLIENT_SECRET=SEU_CLIENT_SECRET_EMPRESA1
BLING2_CLIENT_ID=SEU_CLIENT_ID_EMPRESA2
BLING2_CLIENT_SECRET=SEU_CLIENT_SECRET_EMPRESA2
BLING_REDIRECT_URI=http://127.0.0.1:5050/callback
3) python app.py
4) Abra http://127.0.0.1:5050 e conecte Empresa 1 ou 2

import os
from dotenv import load_dotenv
load_dotenv()
class Settings:
    BLING_CLIENT_ID=os.getenv('BLING_CLIENT_ID','').strip()
    BLING_CLIENT_SECRET=os.getenv('BLING_CLIENT_SECRET','').strip()
    BLING_REDIRECT_URI=os.getenv('BLING_REDIRECT_URI','').strip()
    FLASK_SECRET_KEY=os.getenv('FLASK_SECRET_KEY','dev-secret')
    PORT=int(os.getenv('FLASK_RUN_PORT','5050'))
settings=Settings()

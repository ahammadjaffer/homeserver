import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'serverproject.settings')

from waitress import serve
from serverproject.wsgi import application

if __name__ == '__main__':
    print("Starting Waitress internally on http://127.0.0.1:8000 ...")
    serve(
        application,
        host='127.0.0.1',  # Bind locally; Nginx handles network traffic
        port=8000,
        threads=8,
        channel_timeout=60,
        send_bytes=18000,
        max_request_body_size=10737418240  # 10 GB upload limit
    )
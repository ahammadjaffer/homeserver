# run.py
import os
from waitress import serve
from serverproject.wsgi import application

if __name__ == '__main__':
    print("Starting Waitress server on http://0.0.0.0:8000...")
    serve(
        application,
        host='0.0.0.0',
        port=8000,
        max_body_size=10737418240,  # 10 GB limit (in bytes)
        threads=8                   # Optional: allows handling multiple concurrent requests smoothly
    )

import setup_environment

# main.py
import uvicorn
import webbrowser
import threading
from api.server import app
from config import HOST, PORT
import os
from pathlib import Path

def open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")

if __name__ == "__main__":
    # Abrir navegador 2 segundos después de iniciar
    threading.Timer(2.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
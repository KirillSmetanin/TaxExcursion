import requests
import time
import os
from threading import Thread
from datetime import datetime

def ping_self():
    """Периодически пингует приложение чтобы не засыпало"""
    url = os.environ.get('RENDER_EXTERNAL_URL', 'https://taxexcursion.ru')
    
    while True:
        try:
            response = requests.get(f"{url}/health", timeout=10)
            print(f"[{datetime.now()}] Keep-alive ping: {response.status_code}")
        except Exception as e:
            print(f"[{datetime.now()}] Keep-alive failed: {e}")
        
        # Ждем 5 минут (300 секунд) - Render free tier спит после 15 минут неактивности
        time.sleep(300)  # 5 минут

if __name__ == '__main__':
    print("Starting keep-alive service...")
    
    # Запускаем в фоне
    thread = Thread(target=ping_self, daemon=True)
    thread.start()
    
    # Держим основной поток активным
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Keep-alive service stopped.")
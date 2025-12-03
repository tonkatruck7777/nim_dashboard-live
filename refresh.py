# refresh_runner.py
import requests
import os

# Render provides site URL via environment variables if needed
BASE_URL = os.getenv("NIM_DASHBOARD_URL", "https://nim-dashboard.onrender.com")

REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")

if not REFRESH_TOKEN:
    raise RuntimeError("REFRESH_TOKEN env variable not set.")

url = f"{BASE_URL}/refresh/{REFRESH_TOKEN}"

print(f"Calling refresh URL: {url}")

resp = requests.get(url, timeout=600)

print("Status:", resp.status_code)
print("Response:", resp.text)

import os
import sys
import json
import time
import base64
import hashlib
import secrets
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")
CLIENT_FILE = os.path.join(BASE_DIR, "client_config.json")

AUTH_SERVER = "https://mcp.pluang.com"
REG_ENDPOINT = f"{AUTH_SERVER}/register"
AUTH_ENDPOINT = f"{AUTH_SERVER}/authorize"
TOKEN_ENDPOINT = f"{AUTH_SERVER}/token"
REDIRECT_URI = "http://localhost:8080/callback"

def get_or_create_client():
    if os.path.exists(CLIENT_FILE):
        try:
            with open(CLIENT_FILE, "r") as f:
                data = json.load(f)
                if data.get("client_id"):
                    return data["client_id"]
        except Exception:
            pass

    print("[*] Mendaftarkan aplikasi client baru ke Pluang OAuth...")
    payload = {
        "client_name": "PluangAgenticTradingBot",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none"
    }
    resp = requests.post(REG_ENDPOINT, json=payload)
    if resp.status_code in [200, 201]:
        data = resp.json()
        client_id = data.get("client_id")
        with open(CLIENT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Client ID berhasil didaftarkan: {client_id}")
        return client_id
    else:
        raise Exception(f"Gagal mendaftar client ke Pluang: {resp.text}")

def generate_pkce():
    # 64 random bytes -> 86 base64url chars
    code_verifier = secrets.token_urlsafe(64)
    # sha256
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return code_verifier, code_challenge

auth_code_holder = {}

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            qs = parse_qs(parsed.query)
            if "code" in qs:
                auth_code_holder["code"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <html>
                <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0f172a; color:#f8fafc;">
                    <h1 style="color:#22c55e;"> Login Berhasil!</h1>
                    <p style="font-size:18px;">Akun Pluang Anda berhasil terhubung dengan aman ke Bot Trading AI.</p>
                    <p style="color:#94a3b8;">Anda boleh menutup tab browser ini dan kembali ke terminal/chat.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            elif "error" in qs:
                auth_code_holder["error"] = qs["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>Error: {qs['error'][0]}</h1>".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Mute standard http logs to keep terminal clean
        return

def refresh_tokens(refresh_token, client_id):
    print("[*] Memperbarui Access Token Pluang menggunakan Refresh Token...")
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id
    }
    resp = requests.post(TOKEN_ENDPOINT, data=data)
    if resp.status_code == 200:
        token_data = resp.json()
        token_data["acquired_at"] = time.time()
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)
        print("[+] Access token berhasil diperbarui.")
        return token_data
    else:
        print("[-] Gagal refresh token, perlu login ulang.")
        return None

def login_pluang():
    client_id = get_or_create_client()

    # Cek apakah token lama masih ada dan valid
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                token_data = json.load(f)
            expires_in = token_data.get("expires_in", 3600)
            acquired_at = token_data.get("acquired_at", 0)
            if time.time() - acquired_at < (expires_in - 300):
                print("[+] Token Pluang masih valid, tidak perlu login ulang.")
                return token_data.get("access_token")
            elif "refresh_token" in token_data:
                refreshed = refresh_tokens(token_data["refresh_token"], client_id)
                if refreshed:
                    return refreshed.get("access_token")
        except Exception as e:
            print(f"[*] Parsing token error: {e}")

    # Flow login baru via PKCE
    code_verifier, code_challenge = generate_pkce()
    scopes = "market:read portfolio:read trade:write"

    auth_url = (
        f"{AUTH_ENDPOINT}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scopes.replace(' ', '%20')}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )

    with open(os.path.join(BASE_DIR, "login_url.txt"), "w") as f:
        f.write(auth_url)

    print("\n" + "="*60, flush=True)
    print(" SILAKAN LOGIN PLUANG DI BROWSER ANDA", flush=True)
    print("="*60, flush=True)
    print("Jika browser tidak terbuka otomatis, salin URL ini:", flush=True)
    print(f"\n{auth_url}\n", flush=True)
    print("="*60, flush=True)
    print("Menunggu konfirmasi login dari browser...", flush=True)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    webbrowser.open(auth_url)

    # Handle single request
    while "code" not in auth_code_holder and "error" not in auth_code_holder:
        server.handle_request()

    if "error" in auth_code_holder:
        raise Exception(f"Login dibatalkan atau error: {auth_code_holder['error']}")

    code = auth_code_holder["code"]
    print("[+] Kode otentikasi diterima dari Pluang! Menukarkan dengan Token...")

    # Exchange code for token
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier
    }

    resp = requests.post(TOKEN_ENDPOINT, data=token_payload)
    if resp.status_code == 200:
        token_data = resp.json()
        token_data["acquired_at"] = time.time()
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)
        print("[+] SUKSES! Token Pluang berhasil disimpan di tokens.json")
        return token_data.get("access_token")
    else:
        raise Exception(f"Gagal menukarkan token: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    token = login_pluang()
    print(f"\nSiap digunakan! Access Token didapatkan.")

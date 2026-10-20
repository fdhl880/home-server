import os
import sys
import json
import time
import base64
import hashlib
import secrets
import webbrowser
import threading
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
            with open(CLIENT_FILE, "r", encoding="utf-8") as f:
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
    resp = requests.post(REG_ENDPOINT, json=payload, timeout=15)
    if resp.status_code in [200, 201]:
        data = resp.json()
        client_id = data.get("client_id")
        with open(CLIENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Client ID berhasil didaftarkan: {client_id}")
        return client_id
    else:
        raise Exception(f"Gagal mendaftar client ke Pluang: {resp.text}")

def generate_pkce():
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return code_verifier, code_challenge

def is_token_active(token: str) -> bool:
    """Verifikasi token langsung ke server Pluang MCP"""
    if not token:
        return False
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "TokenValidator", "version": "1.0"}
            }
        }
        resp = requests.post(f"{AUTH_SERVER}/mcp", headers=headers, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception:
        return False

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
                    <h1 style="color:#22c55e;">✅ Login Berhasil!</h1>
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
        return

def refresh_tokens(refresh_token, client_id):
    print("[*] Memperbarui Access Token Pluang menggunakan Refresh Token...")
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id
    }
    try:
        resp = requests.post(TOKEN_ENDPOINT, data=data, timeout=15)
        if resp.status_code == 200:
            token_data = resp.json()
            token_data["acquired_at"] = time.time()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            print("[+] Access token berhasil diperbarui.")
            return token_data
        else:
            print(f"[-] Gagal refresh token ({resp.status_code}): {resp.text[:100]}")
            return None
    except Exception as e:
        print(f"[-] Network error saat refresh token: {e}")
        return None

def login_pluang(force=False):
    client_id = get_or_create_client()

    # Cek apakah token lama masih ada dan valid secara live di server Pluang
    if not force and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                token_data = json.load(f)
            token = token_data.get("access_token")
            if token and is_token_active(token):
                print("[+] Token Pluang masih AKTIF & VALID di server Pluang. Siap digunakan!")
                return token
            elif "refresh_token" in token_data:
                print("[*] Token lokal expired. Mencoba refresh token...")
                refreshed = refresh_tokens(token_data["refresh_token"], client_id)
                if refreshed and is_token_active(refreshed.get("access_token")):
                    print("[+] Token berhasil direfresh dan diverifikasi aktif!")
                    return refreshed.get("access_token")
        except Exception as e:
            print(f"[*] Parsing token error: {e}")

    # Flow login baru via PKCE
    print("[*] Memulai sesi otorisasi OAuth baru...")
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

    with open(os.path.join(BASE_DIR, "login_url.txt"), "w", encoding="utf-8") as f:
        f.write(auth_url)
    with open(os.path.join(BASE_DIR, "pending_auth.json"), "w", encoding="utf-8") as f:
        json.dump({"client_id": client_id, "code_verifier": code_verifier, "url": auth_url}, f, indent=2)

    print("\n" + "="*70, flush=True)
    print("🔑 SILAKAN LOGIN KE AKUN PLUANG ANDA DI BROWSER", flush=True)
    print("="*70, flush=True)
    print("Salin URL ini dan buka di browser (Chrome / Edge / Firefox):", flush=True)
    print(f"\n{auth_url}\n", flush=True)
    print("="*70, flush=True)

    # Start local HTTP server in a daemon thread
    server = None
    try:
        server = HTTPServer(("0.0.0.0", 8080), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print("[*] Server callback lokal aktif di port 8080...", flush=True)
    except Exception as e:
        print(f"[!] Info: Port 8080 busy ({e}), Anda dapat paste URL callback secara manual.", flush=True)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Non-blocking input loop with automatic detection
    print("\n💡 Petunjuk:")
    print("1. Login dan setujui izin trading di browser.")
    print("2. Browser akan otomatis redirect ke http://localhost:8080/callback?code=...")
    print("3. Jika browser tidak otomatis redirect (misal di Android), salin URL hasil redirect atau kode authorization, lalu paste di bawah:")
    
    # Wait for either server callback OR manual paste
    code = None
    while not code:
        if "code" in auth_code_holder:
            code = auth_code_holder["code"]
            break
        if "error" in auth_code_holder:
            raise Exception(f"Login ditolak oleh Pluang: {auth_code_holder['error']}")

        time.sleep(1)
        if sys.stdin.isatty():
            try:
                import select
                has_input = False
                if sys.platform == "win32":
                    import msvcrt
                    if msvcrt.kbhit():
                        has_input = True
                else:
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        has_input = True

                if has_input:
                    line = sys.stdin.readline().strip()
                    if line:
                        if "code=" in line:
                            parsed = parse_qs(urlparse(line).query)
                            code = parsed.get("code", [line])[0]
                        else:
                            code = line
                        break
            except Exception:
                pass

    if server:
        try:
            server.shutdown()
        except Exception:
            pass

    print("[+] Kode otentikasi diterima dari Pluang! Menukarkan dengan Token...")

    # Exchange code for token
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier
    }

    resp = requests.post(TOKEN_ENDPOINT, data=token_payload, timeout=15)
    if resp.status_code == 200:
        token_data = resp.json()
        token_data["acquired_at"] = time.time()
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        print("[+] SUKSES! Token Pluang berhasil disimpan di tokens.json")
        return token_data.get("access_token")
    else:
        raise Exception(f"Gagal menukarkan token: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    if "--code" in sys.argv or "-c" in sys.argv:
        flag = "--code" if "--code" in sys.argv else "-c"
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            raw_arg = sys.argv[idx + 1]
            if "code=" in raw_arg:
                code_val = parse_qs(urlparse(raw_arg).query).get("code", [raw_arg])[0]
            else:
                code_val = raw_arg
            
            pending_file = os.path.join(BASE_DIR, "pending_auth.json")
            if not os.path.exists(pending_file):
                print("[-] File pending_auth.json tidak ditemukan. Silakan generate auth URL terlebih dahulu.")
                sys.exit(1)
            with open(pending_file, "r", encoding="utf-8") as f:
                pending = json.load(f)
            
            token_payload = {
                "grant_type": "authorization_code",
                "client_id": pending["client_id"],
                "code": code_val,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": pending["code_verifier"]
            }
            resp = requests.post(TOKEN_ENDPOINT, data=token_payload, timeout=15)
            if resp.status_code == 200:
                token_data = resp.json()
                token_data["acquired_at"] = time.time()
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(token_data, f, indent=2)
                print("[+] SUKSES! Token Pluang berhasil disimpan di tokens.json")
                sys.exit(0)
            else:
                print(f"[-] Gagal menukarkan token: {resp.status_code} - {resp.text}")
                sys.exit(1)

    force_login = "--force" in sys.argv or "-f" in sys.argv
    token = login_pluang(force=force_login)
    print(f"\n✅ Siap digunakan! Token Pluang aktif.")


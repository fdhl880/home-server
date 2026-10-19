import os
import sys
import json
import requests
def load_env_file(filepath=".env"):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_env_file(os.path.join(BASE_DIR, ".env"))

from auth_pluang import login_pluang
from pluang_mcp import PluangMCPClient

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash")

if not OPENROUTER_API_KEY:
    print("[!] Error: OPENROUTER_API_KEY belum disetel di file .env")
    sys.exit(1)

def call_openrouter(messages, tools=None):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 2048
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        raise Exception(f"OpenRouter Error {resp.status_code}: {resp.text}")
    
    data = resp.json()
    choice = data["choices"][0]
    return choice["message"]

def main():
    print("="*65)
    print("🚀 SELAMAT DATANG DI AI AGENTIC TRADING BOT (PLUANG + DEEPSEEK)")
    print("="*65)
    print(f"[*] Model AI: {MODEL}")

    # 1. Otentikasi ke Pluang
    print("[*] Menghubungkan ke akun Pluang...")
    access_token = login_pluang()

    # 2. Inisialisasi MCP Pluang
    print("[*] Menginisialisasi Model Context Protocol (MCP) Pluang...")
    mcp_client = PluangMCPClient(access_token)
    mcp_client.initialize()

    # 3. Dapatkan daftar tools
    tools = mcp_client.get_openai_tools()
    print(f"[+] Berhasil memuat {len(tools)} tools dari Pluang MCP:")
    for t in tools:
        fn = t["function"]
        print(f"    - {fn['name']}: {fn['description']}")

    # 4. System Prompt
    system_prompt = (
        "Anda adalah asisten AI Agentic Trading cerdas untuk akun investasi Pluang. "
        "Anda memiliki akses langsung ke tools resmi Pluang melalui Model Context Protocol (MCP). "
        "Anda dapat memeriksa portofolio, saldo kas, performa aset (Saham US, Crypto, Reksa Dana, Emas), "
        "menganalisis tren pasar, dan membantu menyiapkan draf transaksi jika diminta pengguna. "
        "Aturan Penting: "
        "1. Selalu bersikap objektif, hati-hati terhadap risiko, dan gunakan bahasa Indonesia yang jelas & ramah. "
        "2. Jangan pernah melakukan eksekusi tanpa menjelaskan detail angka (harga, jumlah, biaya). "
        "3. Berikan analisis berbasis data yang Anda peroleh langsung dari tools Pluang."
    )

    conversation_history = [
        {"role": "system", "content": system_prompt}
    ]

    print("\n" + "="*65)
    print("💬 AI Siap Digunakan! Ketik pertanyaan atau instruksi Anda.")
    print("Contoh:")
    print("  - 'Cek portofolio dan sisa saldo kas saya'")
    print("  - 'Bagaimana performa aset crypto saya?'")
    print("  - 'Bandingkan saham Apple dan Nvidia hari ini'")
    print("Ketik 'exit' atau 'keluar' untuk menghentikan program.")
    print("="*65 + "\n")

    while True:
        try:
            user_input = input("\nAnda: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "keluar", "quit"]:
                print("Sampai jumpa dan salam cuan!")
                break

            conversation_history.append({"role": "user", "content": user_input})
            print("\n🤖 DeepSeek sedang menganalisis...")

            # AI Call Loop (handling function calling)
            while True:
                msg = call_openrouter(conversation_history, tools=tools if tools else None)

                # Cek jika AI ingin memanggil tool
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    conversation_history.append(msg)
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except Exception:
                            args = {}
                        
                        print(f"    ⚡ [MCP Tool]: Memanggil '{func_name}' dengan argumen: {args}...")
                        try:
                            tool_result = mcp_client.call_tool(func_name, args)
                            result_str = json.dumps(tool_result, ensure_ascii=False)
                        except Exception as e:
                            result_str = json.dumps({"error": str(e)})
                            print(f"    ❌ Error memanggil tool: {e}")

                        conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": func_name,
                            "content": result_str
                        })
                    # Lanjut looping agar AI bisa menyimpulkan hasil dari tool
                    continue
                else:
                    # AI sudah memberikan jawaban teks final
                    reply = msg.get("content")
                    if not reply and "reasoning" in msg:
                        # Fallback jika model DeepSeek mengisi field reasoning saja
                        reply = msg.get("reasoning")

                    print(f"\nAI: {reply}\n")
                    conversation_history.append({"role": "assistant", "content": reply})
                    break

        except KeyboardInterrupt:
            print("\nKeluar...")
            break
        except Exception as e:
            print(f"\n[!] Terjadi kesalahan: {e}")

if __name__ == "__main__":
    main()

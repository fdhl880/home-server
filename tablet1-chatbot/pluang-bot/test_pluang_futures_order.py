"""
===========================================================================
PYROFUEL TEST SCRIPT: PLUANG CRYPTO FUTURES ORDER EXECUTION
===========================================================================
Uji coba langsung pengiriman order FUTURES (Bukan Spot!) ke Pluang MCP:
- Mode: FUTURES
- Leverage: 5x - 25x
- Margin: ISOLATED
- Direction: LONG & SHORT support
- Currency: USDT / IDR Cash
===========================================================================
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from pluang_mcp import PluangMCPClient

def test_futures_execution(test_symbol="BTC", direction="LONG", test_amount_idr=50000, leverage=5):
    print("=" * 70)
    print("🔥 UJI PEMBELIAN / ORDER ASET FUTURES PLUANG (BUKAN SPOT)")
    print("=" * 70)
    
    token_path = os.path.join(BASE_DIR, "tokens.json")
    if not os.path.exists(token_path):
        print("❌ tokens.json tidak ditemukan! Silakan hubungkan akun Pluang.")
        return False
        
    with open(token_path, "r", encoding="utf-8") as f:
        token_data = json.load(f)
        
    access_token = token_data.get("access_token", "")
    print(f"[*] Access Token ditemukan (panjang: {len(access_token)})")
    
    client = PluangMCPClient(access_token=access_token)
    
    # 1. Test Inisialisasi & Session
    print("\n[1/4] Menginisialisasi session Pluang MCP...")
    try:
        init_res = client.initialize()
        print(f"✅ Inisialisasi sukses: {init_res.get('serverInfo', {})}")
    except Exception as e:
        print(f"⚠️ Init notice: {e}")
        
    sess_id = client._get_chat_session_id()
    print(f"✅ Chat Session ID: {sess_id}")
    
    # 2. Cek Saldo Dompet (Wallet Balance)
    print("\n[2/4] Mengecek Saldo Dompet Pluang (USD Cash / IDR)...")
    try:
        bal = client.get_balance()
        print(f"✅ Saldo Pluang: {bal}")
    except Exception as e:
        print(f"⚠️ Cek saldo: {e}")

    # 3. Uji Setting Leverage & Margin Futures
    print(f"\n[3/4] Mengatur Parameter Futures: Symbol={test_symbol}, Leverage={leverage}x, Margin=ISOLATED...")
    lev_res = client.set_leverage(test_symbol, leverage)
    print(f"   Leverage result: {lev_res}")
    
    margin_res = client.set_margin_type(test_symbol, "ISOLATED")
    print(f"   Margin result: {margin_res}")

    # 4. Uji Dispatch Order Futures (LONG)
    print(f"\n[4/4] Mengirim Order FUTURES {direction} {test_symbol} senilai Rp {test_amount_idr:,} (Lev: {leverage}x)...")
    try:
        order_res = client.open_position(
            symbol=test_symbol,
            direction=direction,
            amount=test_amount_idr,
            leverage=leverage,
            order_type="MARKET",
            margin_type="ISOLATED"
        )
        print(f"\n🎯 HASIL EKSEKUSI PLUANG FUTURES:")
        print(json.dumps(order_res, indent=2, ensure_ascii=False))
        return order_res
    except Exception as e:
        print(f"\n❌ Gagal eksekusi: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    side = sys.argv[2] if len(sys.argv) > 2 else "LONG"
    test_futures_execution(test_symbol=sym, direction=side, test_amount_idr=50000, leverage=5)

"""
Crypto Breaking News & Macro Sentiment Sentinel
Fetches real-time headlines from CoinTelegraph, CoinDesk, and Decrypt feeds.
Performs AI / Quantitative Sentiment Analysis on crypto market news.
"""
import requests
import xml.etree.ElementTree as ET
import time
import re
from datetime import datetime, timezone

NEWS_CACHE = {
    "articles": [],
    "last_fetched": 0,
    "ttl": 120,  # 2 minutes cache
    "market_sentiment": "NEUTRAL",
    "sentiment_score": 50,
    "breaking_alert": None
}

BULLISH_KEYWORDS = [
    "etf", "inflow", "surge", "rally", "breakout", "ath", "all-time high", "bull", "buying",
    "accumulat", "soar", "gain", "jump", "approval", "adoption", "invest", "pump",
    "positive", "green", "climb", "expansion", "support", "record high"
]

BEARISH_KEYWORDS = [
    "crash", "plunge", "dump", "ban", "hack", "exploit", "outflow", "bear", "lawsuit",
    "sec", "subpoena", "fraud", "investigation", "bankrupt", "drop", "sink", "selloff",
    "liquidat", "down", "slump", "fear", "warning", "breach", "shutdown", "recession"
]

def fetch_crypto_news(limit_per_source=5):
    """Fetch real-time headlines from premier crypto news sources."""
    now = time.time()
    if now - NEWS_CACHE["last_fetched"] < NEWS_CACHE["ttl"] and NEWS_CACHE["articles"]:
        return NEWS_CACHE["articles"]

    sources = [
        {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
        {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"name": "Decrypt", "url": "https://decrypt.co/feed"}
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PyroFuelNews/3.0"}
    all_articles = []

    for src in sources:
        try:
            r = requests.get(src["url"], headers=headers, timeout=6)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                items = root.findall(".//item")[:limit_per_source]
                for it in items:
                    title_elem = it.find("title")
                    link_elem = it.find("link")
                    pub_elem = it.find("pubDate")
                    desc_elem = it.find("description")
                    
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                    
                    if title:
                        clean_desc = re.sub('<[^<]+?>', '', desc)[:160] if desc else ""
                        all_articles.append({
                            "source": src["name"],
                            "title": title,
                            "link": link,
                            "pub_date": pub,
                            "snippet": clean_desc,
                            "timestamp": int(now)
                        })
        except Exception:
            pass

    if all_articles:
        bull_hits = 0
        bear_hits = 0
        breaking_alert = None

        for art in all_articles:
            txt = (art["title"] + " " + art["snippet"]).lower()
            b_cnt = sum(1 for kw in BULLISH_KEYWORDS if kw in txt)
            br_cnt = sum(1 for kw in BEARISH_KEYWORDS if kw in txt)
            bull_hits += b_cnt
            bear_hits += br_cnt
            
            art["sentiment"] = "BULLISH" if b_cnt > br_cnt else ("BEARISH" if br_cnt > b_cnt else "NEUTRAL")
            if "sec" in txt or "ban" in txt or "hack" in txt or "crash" in txt:
                breaking_alert = art["title"]

        total = bull_hits + bear_hits
        score = round((bull_hits / total * 100), 1) if total > 0 else 50.0
        
        if score >= 60:
            m_sentiment = "BULLISH"
        elif score <= 40:
            m_sentiment = "BEARISH"
        else:
            m_sentiment = "NEUTRAL"

        NEWS_CACHE["articles"] = all_articles
        NEWS_CACHE["last_fetched"] = now
        NEWS_CACHE["market_sentiment"] = m_sentiment
        NEWS_CACHE["sentiment_score"] = score
        NEWS_CACHE["breaking_alert"] = breaking_alert

    return NEWS_CACHE["articles"]

def get_news_sentiment_summary():
    """Return consolidated macro news sentiment."""
    articles = fetch_crypto_news()
    return {
        "market_sentiment": NEWS_CACHE["market_sentiment"],
        "sentiment_score": NEWS_CACHE["sentiment_score"],
        "total_articles": len(articles),
        "breaking_alert": NEWS_CACHE["breaking_alert"],
        "latest_headline": articles[0]["title"] if articles else "No news available",
        "top_articles": articles[:8],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }

if __name__ == "__main__":
    summary = get_news_sentiment_summary()
    print("Market Sentiment:", summary["market_sentiment"], f"({summary['sentiment_score']}/100)")
    print("Latest Headline:", summary["latest_headline"])
    print("Total Articles:", summary["total_articles"])
    for a in summary["top_articles"][:3]:
        print(f"[{a['source']}] {a['title']} -> {a['sentiment']}")

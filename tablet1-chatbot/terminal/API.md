# PYRO Terminal – API Contract (WP1+WP2)

Base: same origin as the dashboard server (`http://<host>:4000`). All REST is `GET`, JSON.
Module: `terminal/api/index.js`, mounted from `server.js` (guarded). No dummy data: if a source fails the field is `null`, `status` is `"N/A"` and `error` explains.

## Envelope (every REST response)
```json
{ "ok": true, "source": "binance-spot", "ts": 1700000000000, "mode": "LIVE|DELAYED|EOD|N/A",
  "status": "OK|N/A|PARTIAL", "error": null, "data": ... }
```
`ts` = server epoch ms when payload was produced. Items inside `data` carry their own `ts`/`source` when relevant.

## Tick schema (normalized, REST + WS)
```json
{ "symbol":"BTCUSDT", "asset":"crypto|crypto-perp|equity|index|forex|commodity|bond",
  "price":67000.1, "bid":67000.0, "ask":67000.2, "vol":12345.6,
  "chg":120.5, "chgPct":0.18, "high":..., "low":..., "open":..., "prevClose":...,
  "ts":1700000000000, "source":"binance-spot", "mode":"LIVE|DELAYED" }
```
Missing numeric fields are `null`. `vol` = 24h (crypto) / session (others) volume.

## Symbol conventions
- Crypto spot: `BTCUSDT`. Crypto perpetual futures: `BTCUSDT.P` (or `&market=futures`).
- Equities `AAPL`; indices `^GSPC`, `^DJI`, `^IXIC`, `^N225`, `^JKSE`; forex `EURUSD=X`; commodities `GC=F`, `CL=F`; bonds/yields `^TNX`, `^FVX`, `^TYX` (Yahoo style).

## REST
| Route | Params | `data` |
|---|---|---|
| `/api/terminal/quote` | `symbols=A,B,C` (max 50) | `Tick[]` (failed symbols appear as `{symbol,price:null,status:"N/A",error}`) |
| `/api/terminal/kline` | `symbol`, `interval` (1m,5m,15m,1h,4h,1d,1w), `limit` (≤1000), `market=spot\|futures` | `{symbol,interval,candles:[{t,o,h,l,c,v}]}` (t = open time ms) |
| `/api/terminal/depth` | `symbol`, `limit` (≤100) | `{symbol,bids:[[price,qty]],asks:[[price,qty]],ts}` (crypto only) |
| `/api/terminal/trades` | `symbol`, `limit` (≤100) | `[{id,price,qty,side:"BUY\|SELL",ts}]` (crypto only) |
| `/api/terminal/news` | `q` (filter), `cat=general\|crypto\|markets`, `limit` (≤100) | `[{id,title,url,publisher,ts,category,summary}]`, deduped, newest first |
| `/api/terminal/macro` | `series=DGS10,CPIAUCSL,...` or `curve=1` | `{series:{ID:{title,unit,obs:[{date,value}]}}}` / `{curve:[{tenor,series,value,date}]}`; uses FRED API if `FRED_KEY`, else FRED public CSV |
| `/api/terminal/calendar` | `week=this\|next`, `impact=High\|Medium\|Low` | `[{title,country,impact,ts,forecast,previous,actual}]` |
| `/api/terminal/movers` | `asset=crypto\|crypto-perp\|equity`, `dir=gainers\|losers\|active`, `limit` | `Tick[]` |
| `/api/terminal/search` | `q` | `[{symbol,name,asset,exchange,source}]` |
| `/api/terminal/fng` | – | `{value,label,ts,history?}` (alternative.me) |
| `/api/terminal/health` | – | provider status table (see below) |

### Health
```json
{ "ok":true, "source":"hub","ts":..., "data":{
  "uptimeSec":..., "wsClients":2, "wsSubscriptions":5,
  "providers":{ "binance-spot":{"status":"UP|DOWN|DISABLED|UNKNOWN","latencyMs":120,"lastOk":ts,"lastError":null,"mode":"LIVE"}, "...":{} },
  "keys":{"FINNHUB_KEY":false,"TWELVE_KEY":false,"FRED_KEY":false,"CRYPTOPANIC_KEY":false} } }
```
Providers: `binance-spot`, `binance-futures`, `yahoo`, `finnhub`, `twelvedata`, `fred`, `news-rss`, `cryptopanic`, `calendar`, `feargreed`.
Rate limit: 120 req/min/IP on REST → HTTP 429 `{ok:false,error:"rate_limited",retryAfterSec}`.

## WebSocket `ws://<host>:4000/terminal/ws`
Client → server (JSON):
```json
{"op":"subscribe","channels":["ticker:BTCUSDT","ticker:AAPL","kline:BTCUSDT:1m","depth:BTCUSDT","trades:BTCUSDT.P"]}
{"op":"unsubscribe","channels":["ticker:AAPL"]}
{"op":"ping"}
```
Server → client:
```json
{"type":"hello","ts":..,"channels":["ticker","kline","depth","trades"]}
{"type":"subscribed","channels":[...],"rejected":[{"channel":"..","reason":".."}]}
{"type":"tick","channel":"ticker:BTCUSDT","data":Tick}
{"type":"kline","channel":"kline:BTCUSDT:1m","data":{"t","o","h","l","c","v","closed":false,"ts","source","mode"}}
{"type":"depth","channel":"depth:BTCUSDT","data":{"bids":[[p,q]],"asks":[[p,q]],"ts","source","mode"}}
{"type":"trade","channel":"trades:BTCUSDT","data":{"id","price","qty","side","ts","source","mode"}}
{"type":"status","provider":"binance-spot","status":"UP|DOWN","ts":..}
{"type":"pong","ts":..}
```
- Crypto channels = Binance streams (LIVE). Equities/forex/etc. `ticker` = Finnhub WS if `FINNHUB_KEY` (LIVE, US stocks) else Yahoo polling every 5 s (`mode:"DELAYED"`).
- Upstream reconnects automatically (exp. backoff) and re-subscribes; a `status` message is pushed on state change. Max 100 channels per client.
- Server heartbeat: ws ping every 25 s.

## Env keys (never committed)
`FINNHUB_KEY`, `TWELVE_KEY`, `FRED_KEY`, `CRYPTOPANIC_KEY`. All optional; keyless fallbacks used (Yahoo, FRED CSV, RSS).
DNS: if system DNS resolution of a Binance host fails, the module falls back to DNS-over-HTTPS (Cloudflare/Google) and connects to the resolved IP with proper SNI.

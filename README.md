# Forex AI Signal Assistant — educational prototype

**NOT a live automated trading system. No broker connection or order execution is present.** The service only receives TradingView BUY/SELL **candidates**, applies guards, records them and optionally sends Telegram alerts with entry/stop/target. No profitability has been established.

## Quick start (Windows PowerShell)

Install Python 3.11+ and extract the folder.

```powershell
cd C:\path\to\forex_signal_ai
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WEBHOOK_TOKEN='CHOOSE_A_LONG_RANDOM_SECRET'
$env:ADMIN_TOKEN='CHOOSE_ANOTHER_LONG_RANDOM_SECRET'
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/status ; server must stay running. For alerts on your phone, configure `$env:TELEGRAM_BOT_TOKEN` and `$env:TELEGRAM_CHAT_ID` before startup, or inspect saved signals in the local SQLite database. Never share bot tokens.

## TradingView

Open TradingView -> Pine Editor, paste `tradingview.pine`, save, add to EURUSD 15m or 45m. Set the Pine input `Webhook token` to the exact `WEBHOOK_TOKEN` used by the server. Create an alert on **Any alert() function call**, set Webhook URL to `https://YOUR-SECURE-HOST/webhook` (not localhost). TradingView webhook settings and plan requirements can change. Use a managed HTTPS reverse proxy/tunnel with auth, rate limiting and appropriate production hardening; never expose an unsecured dev server.

**Calendar is mandatory / fail-closed**: With no freshly maintained `calendar.csv`, the assistant returns NO TRADE. CSV must contain `utc_time,currency,impact,event` in UTC; see `calendar.example.csv`. A real news/calendar provider ingestion process has not been built, so this is NOT live news coverage. The 12-hour file recency check alone does not establish calendar completeness or reliability. The filter covers only known high-impact scheduled events ±30 min, not breaking news.

**Important timing**: TradingView bar `time` is bar OPEN, not close. The prototype checks the timestamp is within 1 hour; for 45m bars and delayed alerts this may need adjustment. Review broker quotes, timezone and alerts before relying on the output.

## Learning

The assistant records candidates in `signals.sqlite3`, but it does not know actual outcomes without a trusted labeled result. POST `/result` with JSON `{ "admin_token":"...", "signal_id":"...", "outcome_r": 1.2 }` after manually or externally reconciling actual completed setup outcomes. `outcome_r` is measured in initial risk units; -1 means a full SL loss.

After 200 labeled trades, run `python train.py`. This builds `model_candidate.pkl`, NOT a deployed model. Manually validate data leakage, out-of-sample performance, regime performance and probabilistic calibration before promotion. The signal server looks for `model.pkl` if deliberately deployed. Historic training does **not** guarantee an edge. The model predicts observed win/loss conditional on features, not profitability after costs. Model deployment is NOT automatic.

## Operational limitations

- Does not watch YouTube videos automatically; see `strategies_from_videos.md`.
- Does not subscribe to real-time news or economic calendars; requires your own licensed live data integration.
- No automated stop/target management: user enters SL/TP manually with their broker.
- No 24/7 uptime unless deployed on reliable always-on infrastructure and actively monitored.
- TradingView alerts are candidate generation; not broker execution.
- Symbols and market hours should be verified. EMA crossing signal frequency can be low.
- No trading advice or assured returns. Start with paper trading and robust out-of-sample testing.

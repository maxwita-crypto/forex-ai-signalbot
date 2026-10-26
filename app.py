"""Forex signal filter: no brokerage endpoints; cannot place orders."""
import csv, datetime as dt, json, os, sqlite3, threading
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
DB = ROOT / "signals.sqlite3"
LOCK = threading.Lock()
TOKEN = os.getenv("WEBHOOK_TOKEN", "")
ADMIN = os.getenv("ADMIN_TOKEN", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
CALENDAR = ROOT / "calendar.csv"
app = FastAPI(title="Forex AI signal filter (signals only)")

with sqlite3.connect(DB) as c:
    c.execute("CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp REAL, rsi REAL, atr REAL, decision TEXT, reason TEXT, outcome_r REAL)")

class Candidate(BaseModel):
    token: str
    signal_id: str = Field(min_length=3,max_length=220)
    symbol: str
    direction: str
    timeframe: str
    bar_time_ms: int
    entry: float = Field(gt=0)
    sl: float = Field(gt=0)
    tp: float = Field(gt=0)
    rsi: float = Field(ge=0,le=100)
    atr: float = Field(gt=0)

class Result(BaseModel):
    signal_id: str
    outcome_r: float = Field(ge=-50,le=100)
    admin_token: str

def important_news(now: dt.datetime, symbol: str):
    """Fail CLOSED if no *fresh* maintained calendar. UTC timestamp, currency, impact."""
    if not CALENDAR.exists(): return True, "No current economic calendar configured"
    # A 12h freshness requirement prevents stale calendars silently being treated as safe.
    age = now.timestamp() - CALENDAR.stat().st_mtime
    if age < -300 or age > 12*3600: return True, "Economic calendar stale (>12h)"
    codes = {symbol[-6:-3],symbol[-3:]}
    if len(symbol)<6: return True,"Unknown symbol"
    try:
        with CALENDAR.open(newline="", encoding="utf-8") as f:
            for e in csv.DictReader(f):
                if e["impact"].strip().lower() != "high" or e["currency"].strip().upper() not in codes: continue
                when = dt.datetime.fromisoformat(e["utc_time"].replace("Z","+00:00"))
                if when.tzinfo is None: return True,"Calendar event without timezone"
                if abs((when-now).total_seconds()) <= 30*60: return True,f"High-impact news: {e.get('event','event')}"
    except Exception:
        return True,"Could not validate calendar"
    return False,""

def ml_guard(c, candidate):
    """Optional trained model, otherwise conservative rules. Model never replaces risk guard."""
    if candidate.rsi < 30 or candidate.rsi > 70: return False, "RSI extreme"
    if abs(candidate.entry-candidate.sl) < 1e-7: return False,"Invalid stop distance"
    rr = abs(candidate.tp-candidate.entry) / abs(candidate.entry-candidate.sl)
    if rr < 1.9: return False,"Risk/reward below 1.9"
    model_path=ROOT / "model.pkl"
    if model_path.exists():
        # Joblib/pickle is unsafe for untrusted files. Only load locally generated model.
        try:
            import joblib
            model=joblib.load(model_path)
            pred=float(model.predict_proba([[candidate.rsi,candidate.atr,rr, 1 if candidate.direction=='BUY' else 0]])[0][1])
            if pred < 0.60: return False,f"Historical model score {pred:.2f} below threshold"
        except Exception: return False,"Model unreadable; fail closed"
    return True, "Checks passed" if not model_path.exists() else "Validated model and base checks passed"

def notify(message):
    if not (TG_TOKEN and TG_CHAT): return "No Telegram configured; signal stored only"
    try:
        r=requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id":TG_CHAT,"text":message}, timeout=8)
        r.raise_for_status(); return "Telegram sent"
    except requests.RequestException: return "Telegram delivery failed (check logs)"

@app.get("/status")
def status():
    with sqlite3.connect(DB) as c:
        count=c.execute("SELECT count(*) FROM signals").fetchone()[0]
    return {"mode":"SIGNALS_ONLY_NO_ORDERS","signals_saved":count,"calendar_present":CALENDAR.exists(),"telegram_configured":bool(TG_TOKEN and TG_CHAT),"ml_model_present":(ROOT/"model.pkl").exists()}

@app.post("/webhook")
def webhook(x: Candidate):
    if not TOKEN or x.token != TOKEN: raise HTTPException(401,"Invalid token")
    if x.direction not in ("BUY","SELL") or x.timeframe not in ("15","45"): raise HTTPException(400,"Unsupported signal")
    if x.direction == "BUY" and not(x.sl < x.entry < x.tp): raise HTTPException(400,"Invalid long SL/TP")
    if x.direction == "SELL" and not(x.tp < x.entry < x.sl): raise HTTPException(400,"Invalid short SL/TP")
    now = dt.datetime.now(dt.timezone.utc)
    bar_dt = dt.datetime.fromtimestamp(x.bar_time_ms/1000,dt.timezone.utc)
    if abs((now-bar_dt).total_seconds()) > 3600: raise HTTPException(400,"Stale bar timestamp")
    # Weekend check, no fresh opens Saturday/Sunday UTC.
    if now.weekday() >= 5: blocked, why=True,"Weekend"
    else: blocked, why=important_news(now,x.symbol)
    good, model_reason=ml_guard(None,x)
    decision="NO TRADE" if blocked or not good else x.direction
    reason=why if blocked else model_reason
    with LOCK, sqlite3.connect(DB) as c:
        found=c.execute("SELECT decision,reason FROM signals WHERE id=?",(x.signal_id,)).fetchone()
        if found: return {"duplicate":True,"decision":found[0],"reason":found[1]}
        c.execute("INSERT INTO signals (id,ts,symbol,direction,entry,sl,tp,rsi,atr,decision,reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (x.signal_id,now.isoformat(),x.symbol,x.direction,x.entry,x.sl,x.tp,x.rsi,x.atr,decision,reason))
    msg=f"{decision} | {x.symbol} ({x.timeframe}m)\nEntry {x.entry} | SL {x.sl} | TP {x.tp}\nFilter: {reason}\nNur Signal, keine Order."
    return {"decision":decision,"reason":reason,"delivery":notify(msg)}

@app.post("/result")
def result(r: Result):
    if not ADMIN or r.admin_token != ADMIN: raise HTTPException(401,"Unauthorized")
    with sqlite3.connect(DB) as c:
        cur=c.execute("UPDATE signals SET outcome_r=? WHERE id=? AND outcome_r IS NULL",(r.outcome_r,r.signal_id))
        if not cur.rowcount: raise HTTPException(404,"Unknown or already labeled")
    return {"saved":True}

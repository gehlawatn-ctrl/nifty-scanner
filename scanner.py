# scanner.py - Nifty 500 6% Scanner + Telegram 9:20 AM
import yfinance as yf, pandas as pd, numpy as np, requests, time, os
from bs4 import BeautifulSoup
from io import StringIO
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
    loss = -delta.where(delta < 0, 0).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
headers = {"User-Agent": "Mozilla/5.0"}
try:
    r = requests.get("https://archives.nseindia.com/content/indices/ind_nifty500list.csv", headers=headers, timeout=10)
    df_u = pd.read_csv(StringIO(r.text))
except:
    df_u = pd.read_csv("https://raw.githubusercontent.com/karthikrangasai/NSE-India-Data/main/ind_nifty500list.csv")
df_u['ticker'] = df_u['Symbol'] + ".NS"
def scan_6pct(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        df['EMA20'] = close.ewm(span=20).mean()
        df['EMA50'] = close.ewm(span=50).mean()
        df['EMA200'] = close.ewm(span=200).mean()
        df['RSI'] = rsi(close)
        df['ATR'] = (high - low).ewm(span=14).mean()
        df['VolAvg20'] = vol.rolling(20).mean()
        df['High20'] = high.rolling(20).max()
        curr = df.iloc[-1]
        price, rsi_val = curr['Close'], curr['RSI']
        atr_pct = (curr['ATR']/price)*100
        cond = [price > curr['EMA20'] > curr['EMA50'] and price > curr['EMA200'], 52 < rsi_val < 70, curr['Volume'] > curr['VolAvg20']*1.2, price >= curr['High20']*0.97, 0.8 < atr_pct < 3.5, price < curr['EMA20']*1.08]
        if sum(cond) >= 5:
            return {'ticker':ticker, 'price':round(price,2), 'target':round(price*1.06,2), 'stop':round(price*0.97,2), 'RSI':round(rsi_val,1), 'vol_x':round(curr['Volume']/curr['VolAvg20'],2), 'score':sum(cond)}
    except: return None
    return None
print("Scanning 500...")
results = []
for t in df_u['ticker'].tolist():
    res = scan_6pct(t)
    if res: results.append(res)
    time.sleep(0.05)
df_6pct = pd.DataFrame(results)
if df_6pct.empty:
    send_telegram("⚠️ *Nifty 500 6% Scanner - 9:20 AM*\nNo setup today.")
    exit()
def get_funda(ticker):
    sym = ticker.replace(".NS","")
    try:
        r = requests.get(f"https://www.screener.in/company/{sym}/", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        data = {}
        for li in soup.select("#top-ratios li"):
            try: data[li.find("span",class_="name").text.strip()] = float(li.find("span",class_="number").text.strip().replace("%","").replace(",",""))
            except: pass
        return data.get("ROE",0), data.get("ROCE",0)
    except: return 0,0
quality = []
for t in df_6pct['ticker'].tolist():
    roe, roce = get_funda(t)
    if roe > 15 and roce > 15: quality.append(t)
    time.sleep(0.7)
df_final = df_6pct[df_6pct['ticker'].isin(quality)].sort_values(['score','vol_x'], ascending=False)
if df_final.empty:
    msg = f"*Nifty 500 6% Scanner - 9:20 AM*\nFound {len(df_6pct)} technical setups, 0 passed quality filter (ROE>15 + ROCE>15)."
else:
    msg = f"*🚀 Nifty 500 6% Scanner - 9:20 AM*\n*Quality Picks: {len(df_final)}/{len(df_6pct)}* (ROE>15 + ROCE>15)\n\n"
    for i, row in df_final.head(10).iterrows():
        msg += f"*{row['ticker']}* ₹{row['price']} → ₹{row['target']} (SL ₹{row['stop']}) | RSI {row['RSI']} | Vol {row['vol_x']}x | Score {row['score']}/6\n"
    msg += f"\n_Entry: CMP | Target +6% | Stop -3% | Risk 1% per trade_"
send_telegram(msg)
print(msg)

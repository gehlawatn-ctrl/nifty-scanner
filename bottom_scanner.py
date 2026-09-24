# bottom_scanner.py - Bottom Reversal Scanner (Oversold + Reversal)
import yfinance as yf, pandas as pd, requests, time, os
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
def is_hammer(row):
    try:
        o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']
        body = abs(c - o)
        rng = h - l
        if rng == 0 or body == 0: return False
        lower = min(o,c) - l
        upper = h - max(o,c)
        return lower > 2*body and upper < 0.35*rng
    except: return False
def scan_bottom(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        df['RSI'] = rsi(df['Close'])
        df['VolAvg20'] = df['Volume'].rolling(20).mean()
        df['High52'] = df['High'].rolling(252).max()
        df['Low52'] = df['Low'].rolling(252).min()
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        price = curr['Close']
        rsi_now = curr['RSI']
        rsi_prev = prev['RSI']
        high52 = curr['High52']
        low52 = curr['Low52']
        ema200 = curr['EMA200']
        vol_ratio = curr['Volume'] / curr['VolAvg20'] if curr['VolAvg20']>0 else 0
        drawdown = ((price - high52)/high52)*100
        near_support = (price <= ema200*1.06 and price >= ema200*0.90) or (price <= low52*1.10)
        hammer = is_hammer(curr)
        engulf = prev['Close'] < prev['Open'] and curr['Close'] > curr['Open'] and curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']
        reversal_candle = hammer or engulf or (curr['Close'] > curr['Open'] and curr['Close'] > prev['Close'])
        cond = [
            drawdown <= -20,
            rsi_now < 40,
            rsi_now > rsi_prev,
            vol_ratio >= 1.5,
            near_support,
            reversal_candle
        ]
        score = sum(cond)
        if score >= 4:
            support = round(ema200 if abs(price-ema200) < abs(price-low52) else low52,2)
            return {'ticker':ticker, 'price':round(price,2), 'high52':round(high52,2), 'drawdown':round(drawdown,1), 'RSI':round(rsi_now,1), 'RSI_prev':round(rsi_prev,1), 'vol_x':round(vol_ratio,2), 'support':support, 'stop':round(support*0.95,2), 'target':round(price*1.12,2), 'score':score, 'hammer':hammer}
    except: return None
    return None
print("Scanning 500 for bottom reversal...")
results = []
for t in df_u['ticker'].tolist():
    res = scan_bottom(t)
    if res: results.append(res)
    time.sleep(0.05)
df_bot = pd.DataFrame(results)
if df_bot.empty:
    send_telegram("🔻 *Bottom Reversal Scanner - 9:20 AM*\nNo bottom reversal setup today. No stock showing strong reversal signal.")
    print("No bottom picks")
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
for t in df_bot['ticker'].tolist():
    roe, roce = get_funda(t)
    if roe > 12 and roce > 12: quality.append(t)
    time.sleep(0.7)
df_final = df_bot[df_bot['ticker'].isin(quality)].sort_values(['score','vol_x'], ascending=False)
if df_final.empty:
    df_final = df_bot.sort_values(['score','vol_x'], ascending=False).head(5)
    note = "_No stock passed ROE>12 filter, showing best technical reversals (check fundamentals manually)_\n\n"
else:
    note = f"*Quality Filter: ROE>12 + ROCE>12 ({len(df_final)}/{len(df_bot)} passed)*\n\n"
msg = f"*🔻 Bottom Reversal Scanner - 9:20 AM*\n{note}"
for i, row in df_final.head(10).iterrows():
    tag = "🔨 Hammer" if row['hammer'] else "📈 Reversal"
    msg += f"*{row['ticker']}* ₹{row['price']} (52W High ₹{row['high52']} {row['drawdown']}%) | RSI {row['RSI_prev']}→{row['RSI']} | Vol {row['vol_x']}x | Support ₹{row['support']} | SL ₹{row['stop']} → Target ₹{row['target']} | Score {row['score']}/6 {tag}\n"
msg += f"\n_Entry: CMP | Target +12% | SL 5% below support | Risk 1% per trade - Bottom is risky, use strict SL_"
send_telegram(msg)
print(msg)

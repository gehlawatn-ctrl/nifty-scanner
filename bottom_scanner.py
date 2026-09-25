# bottom_scanner.py - STRONG Bottom Reversal Scanner - Vol 1.5x + MACD Divergence MANDATORY
import yfinance as yf, pandas as pd, requests, time, os
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

def is_hammer(row):
    try:
        o,h,l,c = row['Open'], row['High'], row['Low'], row['Close']
        body = abs(c-o)
        rng = h-l
        if rng==0 or body==0: return False
        lower = min(o,c)-l
        upper = h-max(o,c)
        return lower > 2*body and upper < 0.35*rng
    except: return False

# Nifty 500 list
headers = {"User-Agent": "Mozilla/5.0"}
try:
    r = requests.get("https://archives.nseindia.com/content/indices/ind_nifty500list.csv", headers=headers, timeout=10)
    df_u = pd.read_csv(StringIO(r.text))
except:
    df_u = pd.read_csv("https://raw.githubusercontent.com/karthikrangasai/NSE-India-Data/main/ind_nifty500list.csv")
df_u['ticker'] = df_u['Symbol'] + ".NS"

def scan_strong(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 210: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Indicators
        df['SMA200'] = df['Close'].rolling(200).mean()
        df['RSI'] = rsi(df['Close'])
        df['VolAvg20'] = df['Volume'].rolling(20).mean()
        # MACD 12,26,9
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']
        # Support = 20 day low (previous)
        df['Support20'] = df['Low'].rolling(20).min()
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev10 = df.iloc[-11]  # 10 days ago for divergence
        
        price = float(curr['Close'])
        support = float(curr['Support20'])
        # 52W High for drawdown
        high52 = float(df['High'].rolling(252).max().iloc[-1])
        drawdown = ((price - high52)/high52)*100
        
        rsi_now = float(curr['RSI'])
        rsi_prev = float(prev['RSI'])
        vol_ratio = float(curr['Volume']/curr['VolAvg20']) if curr['VolAvg20']>0 else 0
        hist = float(curr['Hist'])
        hist_prev = float(prev['Hist'])
        hist_10ago = float(prev10['Hist'])
        price_10ago = float(prev10['Close'])
        
        # ===== STRONG FILTERS - MANDATORY =====
        # 1. Volume MUST be >=1.5x - fail fast
        vol_ok = vol_ratio >= 1.5
        if not vol_ok:
            return None
            
        # 2. Price MUST be above support + Green close
        price_ok = price > support and curr['Close'] > curr['Open']
        if not price_ok:
            return None
        
        # 3. Drawdown -20% to -40% only (avoid -47% broken like ABLBL)
        drawdown_ok = -40 <= drawdown <= -20
        
        # 4. RSI 25-40 and turning UP
        rsi_ok = 25 <= rsi_now <= 40 and rsi_now > rsi_prev
        
        # 5. MACD Bullish - Histogram >0 and rising OR Divergence (price lower low but hist higher low)
        macd_rising = hist > 0 and hist > hist_prev
        divergence = (price < price_10ago) and (hist > hist_10ago) and (hist > hist_prev)
        macd_ok = macd_rising or divergence
        
        hammer = is_hammer(curr)
        green = curr['Close'] > curr['Open']
        reversal = hammer or green
        
        score = sum([vol_ok, price_ok, drawdown_ok, rsi_ok, macd_ok, reversal])
        
        # Need at least 5/6 and MACD must be true
        if drawdown_ok and rsi_ok and macd_ok and score >= 5:
            return {
                'ticker': ticker,
                'price': round(price,2),
                'high52': round(high52,2),
                'drawdown': round(drawdown,1),
                'RSI': round(rsi_now,1),
                'RSI_prev': round(rsi_prev,1),
                'vol_x': round(vol_ratio,2),
                'hist': round(hist,3),
                'support': round(support,2),
                'SL': round(support*0.95,2),
                'Target': round(price*1.12,2),
                'score': score,
                'hammer': hammer,
                'divergence': divergence
            }
    except Exception as e:
        return None
    return None

print("Scanning Nifty 500 STRONG bottom reversal (Vol 1.5x + MACD mandatory)...")
results=[]
for t in df_u['ticker'].tolist():
    res = scan_strong(t)
    if res: results.append(res)
    time.sleep(0.05)

df_res = pd.DataFrame(results)

if df_res.empty:
    msg = "✅ *Bottom Reversal Scanner - 9:25 AM*\n_No STRONG reversal today._\nVol >=1.5x + MACD bullish + Price>Support + RSI 25-40 — koi stock pass nahi kiya. Fake bounce filtered ✅\n\n_Aaj ke jaise 0.05x-0.15x wale sab reject hue — jis din Vol 1.5x + green close + MACD up ek saath aayega tabhi alert ayega._"
    send_telegram(msg)
    print("No strong picks - correctly filtered")
    exit()

df_res = df_res.sort_values(['vol_x','score'], ascending=False)

msg = f"*✅ STRONG Bottom Reversal - 9:25 AM ({len(df_res)} picks)*\n_Vol >=1.5x + MACD bullish + Price>Support MANDATORY_\n\n"
for i,row in df_res.head(10).iterrows():
    tag = "🔨 Hammer" if row['hammer'] else "📈 Reversal"
    div = " + Divergence" if row['divergence'] else ""
    msg += f"*{row['ticker']}* ₹{row['price']} (52W High ₹{row['high52']} {row['drawdown']}%) | RSI {row['RSI_prev']}→{row['RSI']} | Vol {row['vol_x']}x | MACD Hist {row['hist']}{div} | Support ₹{row['support']} | SL ₹{row['SL']} → Target ₹{row['Target']} | Score {row['score']}/6 {tag}\n"

msg += f"\n_Strategy: SL 5% below support compulsory. Target 12% in 5-15 days. Vol 1.5x = big buyers confirmed._"
send_telegram(msg)
print(msg)

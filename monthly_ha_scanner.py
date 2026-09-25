# monthly_ha_scanner.py - Monthly Heikin-Ashi Green after Several Reds
import yfinance as yf, pandas as pd, requests, time, os
from io import StringIO

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def heikin_ashi(df):
    ha = pd.DataFrame(index=df.index)
    ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha['HA_Open'] = 0.0
    ha['HA_Open'].iloc[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha['HA_Open'].iloc[i] = (ha['HA_Open'].iloc[i-1] + ha['HA_Close'].iloc[i-1]) / 2
    ha['HA_High'] = pd.concat([df['High'], ha['HA_Open'], ha['HA_Close']], axis=1).max(axis=1)
    ha['HA_Low'] = pd.concat([df['Low'], ha['HA_Open'], ha['HA_Close']], axis=1).min(axis=1)
    return ha

headers = {"User-Agent": "Mozilla/5.0"}
try:
    r = requests.get("https://archives.nseindia.com/content/indices/ind_nifty500list.csv", headers=headers, timeout=10)
    df_u = pd.read_csv(StringIO(r.text))
except:
    df_u = pd.read_csv("https://raw.githubusercontent.com/karthikrangasai/NSE-India-Data/main/ind_nifty500list.csv")
df_u['ticker'] = df_u['Symbol'] + ".NS"

def scan_monthly_ha(ticker, red_count=3):
    try:
        df = yf.download(ticker, period="3y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 400: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df_m = df.resample('ME').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        if len(df_m) < 10: return None
        ha = heikin_ashi(df_m)
        df_m = pd.concat([df_m, ha], axis=1)
        df_m['HA_Color'] = df_m['HA_Close'] > df_m['HA_Open']
        curr_green = df_m['HA_Color'].iloc[-1] == True
        prev_reds = df_m['HA_Color'].iloc[-(red_count+1):-1] == False
        if curr_green and prev_reds.all():
            return {'ticker': ticker,'price': round(df_m['Close'].iloc[-1],2),'month': df_m.index[-1].strftime('%b %Y'),'HA_Open': round(df_m['HA_Open'].iloc[-1],2),'HA_Close': round(df_m['HA_Close'].iloc[-1],2),'reds': red_count}
    except: return None
    return None

print("Scanning Nifty 500 Monthly HA (3 Reds -> 1 Green)...")
results=[]
for t in df_u['ticker'].tolist():
    res = scan_monthly_ha(t, red_count=3)
    if res: results.append(res)
    time.sleep(0.05)

if not results:
    msg = "📊 *Monthly HA Scanner - 9:30 AM*\n_No Monthly HA reversal today._\n3 consecutive RED HA monthly candles ke baad pehla GREEN HA nahi bana."
    send_telegram(msg)
    print("No picks")
    exit()

df_res = pd.DataFrame(results)
msg = f"*📊 Monthly HA Reversal - {df_res.iloc[0]['month']} ({len(df_res)} picks)*\n_3 RED HA months -> 1st GREEN HA month_\n\n"
for _,row in df_res.iterrows():
    msg += f"*{row['ticker']}* ₹{row['price']} | HA {row['HA_Open']}→{row['HA_Close']} GREEN | {row['reds']} Reds before\n"
msg += "\n_Strategy: Monthly HA green = long-term bottom. SL = HA Low of green month. Hold 3-6 months._"
send_telegram(msg)
print(msg)

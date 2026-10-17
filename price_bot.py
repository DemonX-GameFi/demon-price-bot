import io, json, os, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

TOKEN = '0x2e51b6f3181b342d098b1a939ae1944ed6768fd4'
BASE = 'https://api.geckoterminal.com/api/v2'
HEADERS = {'Accept':'application/json;version=20230203','User-Agent':'DEMONCommunityPriceBot/2.0'}
STATE = Path('last_trade.json')

def fetch(path):
    with urllib.request.urlopen(urllib.request.Request(BASE+path, headers=HEADERS), timeout=30) as r:
        return json.load(r)

def choose_pool():
    data = fetch(f'/networks/bsc/tokens/{TOKEN}/pools?page=1')['data']
    pools=[]
    for p in data:
        a=p.get('attributes',{}); name=(a.get('name') or '').upper()
        if a.get('address') and 'DEMON' in name:
            pools.append((int('USDT' in name or 'USDC' in name), float(a.get('reserve_in_usd') or 0), a['address']))
    if not pools: raise RuntimeError('No DEMON pool available')
    return max(pools)[2]

def parse_time(s):
    return datetime.fromisoformat(s.replace('Z','+00:00'))

def latest_trades(pool):
    rows=fetch(f'/networks/bsc/pools/{pool}/trades').get('data',[])
    out=[]
    for row in rows:
        a=row.get('attributes',{}); t=a.get('block_timestamp')
        if t:
            out.append((parse_time(t), str(row.get('id') or a.get('tx_hash') or ''), a.get('kind')))
    return sorted(out)

def candles_for(pool):
    query=urllib.parse.urlencode({'aggregate':1,'limit':24,'currency':'usd','token':TOKEN})
    rows=fetch(f'/networks/bsc/pools/{pool}/ohlcv/hour?{query}').get('data',{}).get('attributes',{}).get('ohlcv_list',[])
    return sorted([[int(c[0]), *map(float,c[1:6])] for c in rows],key=lambda c:c[0])

def make_chart(candles):
    fig,ax=plt.subplots(figsize=(10,5),dpi=145)
    fig.patch.set_facecolor('#111323');ax.set_facecolor('#111323')
    for i,(_,op,hi,lo,cl,_) in enumerate(candles):
        color='#22c55e' if cl>=op else '#ef5350'
        ax.vlines(i,lo,hi,color=color,lw=1.2)
        ax.add_patch(Rectangle((i-.3,min(op,cl)),.6,max(abs(cl-op),max(cl,op)*1e-5),color=color))
    ax.set_xlim(-1,len(candles));ax.grid(axis='y',alpha=.15)
    idx=list(range(0,len(candles),max(1,len(candles)//5)))
    ax.set_xticks(idx,[datetime.fromtimestamp(candles[i][0],timezone.utc).strftime('%d %b %H:%M') for i in idx],fontsize=8,color='white')
    ax.tick_params(axis='y',colors='white');ax.yaxis.tick_right()
    ax.set_title('DEMON / USD | 1H Candles (UTC)',color='white',loc='left')
    for spine in ax.spines.values():spine.set_visible(False)
    fig.tight_layout();out=io.BytesIO();fig.savefig(out,format='png',facecolor=fig.get_facecolor());plt.close(fig)
    return out.getvalue()

def send_photo(token,chat,png,caption):
    boundary='----DemonPriceUpload2026'
    parts=[]
    for k,v in [('chat_id',chat),('caption',caption)]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="chart.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+png+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendPhoto',data=b''.join(parts),headers={'Content-Type':f'multipart/form-data; boundary={boundary}'},method='POST')
    with urllib.request.urlopen(req,timeout=40) as r:
        result=json.load(r)
    if not result.get('ok'):raise RuntimeError('Telegram sendPhoto failed')

def main():
    pool=choose_pool()
    trades=latest_trades(pool)
    now=datetime.now(timezone.utc)
    old=json.loads(STATE.read_text()) if STATE.exists() else None
    if old and old.get('pool','').lower()!=pool.lower():
        raise RuntimeError('Pool changed; review last_trade.json before switching to prevent duplicate updates')
    # First execution establishes baseline without sending old trades.
    if not old:
        STATE.write_text(json.dumps({'pool':pool,'last_checked_at':now.isoformat()},indent=2)+'\n')
        print('Baseline initialized; no Telegram message sent on first run')
        return
    last_checked=parse_time(old['last_checked_at'])
    # One-hour checks only; never report trades older than 90 minutes.
    cutoff=max(last_checked,now-timedelta(minutes=90))
    fresh=[t for t in trades if cutoff<t[0]<=now]
    if not fresh:
        STATE.write_text(json.dumps({'pool':pool,'last_checked_at':now.isoformat()},indent=2)+'\n')
        print('No new trades since last check; skipped message')
        return
    candles=candles_for(pool)
    if len(candles)<4:raise RuntimeError('Not enough candle history; state not advanced')
    # OHLCV candle timestamp is candle opening time; allow up to 2h of lag.
    if now.timestamp()-candles[-1][0]>7200:
        raise RuntimeError('Candle data is stale; state not advanced, no message sent')
    price=candles[-1][4]
    if price<=0:raise RuntimeError('Invalid price; no message sent')
    buys=sum(1 for t in fresh if t[2]=='buy');sells=sum(1 for t in fresh if t[2]=='sell')
    caption=(f'📊 DEMON / USDT MARKET UPDATE\n\n💰 Latest candle close: ${price:.10g}\n'
             f'🟢 Buys: {buys} | 🔴 Sells: {sells}\n'
             f'🕒 New trades since last check: {len(fresh)}\n'
             f'🕯 1H candles | UTC\n'
             f'📅 Last candle: {datetime.fromtimestamp(candles[-1][0],timezone.utc):%Y-%m-%d %H:%M} UTC\n\n'
             f'📈 https://www.geckoterminal.com/bsc/pools/{pool}\nData: GeckoTerminal')
    token=os.environ['TELEGRAM_BOT_TOKEN'].strip();chat=os.environ['TELEGRAM_CHAT_ID'].strip()
    if not token or not chat:raise RuntimeError('Missing Telegram secrets')
    send_photo(token,chat,make_chart(candles),caption)
    STATE.write_text(json.dumps({'pool':pool,'last_checked_at':now.isoformat()},indent=2)+'\n')
    print(f'Sent chart for {len(fresh)} new trades; state advanced')

if __name__=='__main__':main()

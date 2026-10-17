import io
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

TOKEN = '0x2e51b6f3181b342d098b1a939ae1944ed6768fd4'
BASE = 'https://api.geckoterminal.com/api/v2'
HEADERS = {'Accept': 'application/json;version=20230203', 'User-Agent': 'DEMONCommunityPriceBot/1.0'}

def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)

def choose_pool():
    payload = get_json(f'{BASE}/networks/bsc/tokens/{TOKEN}/pools?page=1')
    candidates = []
    for p in payload.get('data', []):
        a = p.get('attributes', {})
        address = a.get('address')
        if not address: continue
        name = (a.get('name') or '').upper()
        if 'DEMON' not in name: continue
        liquidity = float(a.get('reserve_in_usd') or 0)
        candidates.append((('USDT' in name or 'USDC' in name), liquidity, address, name))
    if not candidates:
        raise RuntimeError('No DEMON BSC pool returned by GeckoTerminal; no message sent')
    candidates.sort(reverse=True)
    return candidates[0][2], candidates[0][3]

def chart(candles, name):
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    fig.patch.set_facecolor('#111323'); ax.set_facecolor('#111323')
    for i, (_, op, hi, lo, cl, _) in enumerate(candles):
        color = '#22c55e' if cl >= op else '#ef5350'
        ax.vlines(i, lo, hi, color=color, linewidth=1.3)
        height = max(abs(cl-op), max(cl, op)*0.00001)
        ax.add_patch(Rectangle((i-.32, min(op,cl)), .64, height, facecolor=color, edgecolor=color))
    ax.set_xlim(-1, len(candles))
    ax.set_xticks(list(range(0, len(candles), max(1, len(candles)//6))))
    ax.set_xticklabels([datetime.fromtimestamp(candles[i][0],timezone.utc).strftime('%d %b %H:%M') for i in ax.get_xticks().astype(int)], rotation=0, fontsize=8, color='#cbd5e1')
    ax.tick_params(axis='y', colors='#cbd5e1', labelsize=9)
    ax.grid(axis='y', color='#64748b', alpha=.22)
    ax.yaxis.tick_right()
    ax.set_title('DEMON / USD  |  1H Candles  |  UTC', color='white', fontsize=15, loc='left', pad=16)
    for spine in ax.spines.values(): spine.set_visible(False)
    fig.tight_layout(pad=2)
    out = io.BytesIO(); fig.savefig(out, format='png', facecolor=fig.get_facecolor()); plt.close(fig)
    return out.getvalue()

def send_photo(bot_token, chat_id, png, caption):
    boundary = '----DEMONPriceBoundary9ad1'
    parts = []
    for key, value in [('chat_id', chat_id), ('caption', caption)]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="demon-chart.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+png+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    body = b''.join(parts)
    url = f'https://api.telegram.org/bot{bot_token}/sendPhoto'
    req = urllib.request.Request(url, data=body, headers={'Content-Type':f'multipart/form-data; boundary={boundary}'}, method='POST')
    with urllib.request.urlopen(req, timeout=35) as resp:
        result = json.load(resp)
    if not result.get('ok'): raise RuntimeError('Telegram did not confirm delivery')

def main():
    bot_token = os.environ['TELEGRAM_BOT_TOKEN'].strip()
    chat_id = os.environ['TELEGRAM_CHAT_ID'].strip()
    if not bot_token or not chat_id: raise RuntimeError('Telegram secrets missing')
    pool, name = choose_pool()
    query = urllib.parse.urlencode({'aggregate':1,'limit':24,'currency':'usd','token':TOKEN})
    payload = get_json(f'{BASE}/networks/bsc/pools/{pool}/ohlcv/hour?{query}')
    raw = payload.get('data',{}).get('attributes',{}).get('ohlcv_list',[])
    candles = sorted([[int(c[0]), *[float(v) for v in c[1:6]]] for c in raw],key=lambda c:c[0])
    if len(candles)<4: raise RuntimeError('Insufficient OHLCV history; no message sent')
    if datetime.now(timezone.utc).timestamp()-candles[-1][0] > 10800:
        raise RuntimeError('Latest candle older than 3 hours; no stale price sent')
    latest = candles[-1][4]
    if latest<=0: raise RuntimeError('Invalid latest close')
    first = candles[0][1]
    change = (latest/first-1)*100 if first>0 else 0
    caption = (f'📊 DEMON MARKET UPDATE\n\n💰 Price (latest 1H close): ${latest:.10g}\n'
               f'📈 Change (chart window): {change:+.2f}%\n'
               f'🕯 1H Candles | BNB Smart Chain\n'
               f'🕒 Last candle: {datetime.fromtimestamp(candles[-1][0],timezone.utc):%Y-%m-%d %H:%M} UTC\n\n'
               f'🔗 https://www.geckoterminal.com/bsc/pools/{pool}\n\nMarket data: GeckoTerminal')
    send_photo(bot_token,chat_id,chart(candles,name),caption)
    print('Successfully sent DEMON chart to Telegram')

if __name__=='__main__': main()

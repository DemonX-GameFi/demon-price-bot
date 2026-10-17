import json
import os
import urllib.parse
import urllib.request

TOKEN = '0x2e51b6f3181b342d098b1a939ae1944ed6768fd4'.lower()
API = f'https://api.dexscreener.com/token-pairs/v1/bsc/{TOKEN}'


def get_json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'DemonPriceBot/1.0'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def main():
    bot_token = os.environ['TELEGRAM_BOT_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
    pairs = get_json(API)
    if not isinstance(pairs, list):
        raise RuntimeError('Unexpected DEX Screener response')
    eligible = [p for p in pairs if p.get('chainId') == 'bsc' and p.get('baseToken', {}).get('address', '').lower() == TOKEN and p.get('priceUsd')]
    if not eligible:
        raise RuntimeError('No BSC pair with DEMON as base token and USD price found; nothing sent')
    preferred = [p for p in eligible if p.get('quoteToken', {}).get('symbol', '').upper() == 'USDT']
    candidates = preferred or eligible
    pair = max(candidates, key=lambda p: float((p.get('liquidity') or {}).get('usd') or 0))
    price = float(pair['priceUsd'])
    change = (pair.get('priceChange') or {}).get('h24')
    volume = (pair.get('volume') or {}).get('h24')
    price_text = f'${price:.10f}'.rstrip('0').rstrip('.') if price < 1 else f'${price:,.6f}'.rstrip('0').rstrip('.')
    change_text = f'{float(change):+.2f}%' if change is not None else 'N/A'
    volume_text = f'${float(volume):,.0f}' if volume is not None else 'N/A'
    chart_url = pair.get('url') or f'https://dexscreener.com/bsc/{pair["pairAddress"]}'
    message = (f'📊 DEMON PRICE UPDATE\n\n'
               f'💰 Price: {price_text}\n'
               f'📈 24H Change: {change_text}\n'
               f'📊 24H Volume: {volume_text}\n\n'
               f'🔗 Live Chart: {chart_url}\n\n'
               f'BNB Smart Chain • DEX Screener')
    endpoint = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    result = get_json(endpoint, urllib.parse.urlencode({'chat_id': chat_id, 'text': message, 'disable_web_page_preview': 'true'}).encode())
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected message')
    print('Price update delivered successfully')


if __name__ == '__main__':
    main()

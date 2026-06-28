#!/bin/bash
# Тест доступа к каналам напрямую с VPS
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

python3 << 'PYEOF'
import urllib.request, urllib.error, urllib.parse, gzip, json

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

CHANNELS = ['CRERussia','officenewsdaily','nedvirf','arendator_ru',
            'pravonadom1','rusipoteka','ria_realty','Commers_Estate']

results = []
for ch in CHANNELS:
    try:
        req = urllib.request.Request(
            f'https://t.me/s/{ch}',
            headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip, deflate'}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            raw = r.read()
            try: body = gzip.decompress(raw)
            except: body = raw
            size = len(body)
            # Проверяем есть ли контент
            has_posts = b'tgme_widget_message' in body
            results.append(f'✅ @{ch}: HTTP {status}, {size//1024}KB, posts={has_posts}')
    except urllib.error.HTTPError as e:
        results.append(f'❌ @{ch}: HTTP {e.code} {e.reason}')
    except urllib.error.URLError as e:
        results.append(f'🔴 @{ch}: URLError {e.reason}')
    except Exception as e:
        results.append(f'⚠️ @{ch}: {type(e).__name__}: {e}')

report = '<b>Диагностика доступа к каналам с VPS:</b>\n\n' + '\n'.join(results)
print('\n'.join(results))
tg(report)
PYEOF

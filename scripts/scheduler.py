#!/usr/bin/env python3
"""
Умный планировщик публикаций Grandvest.

Логика:
- 08:00–21:00 МСК (05:00–18:00 UTC): публикуем сразу после парсинга
- 21:01–07:59 МСК: парсим и складываем в буфер /data/night_buffer.json
- Ровно в 08:00 МСК (05:00 UTC): публикуем всё из буфера + новые новости
- Если пайплайн n8n уже обработал новость — она в дедупликации, повтора не будет
"""
import json, os, datetime, urllib.request, urllib.parse, subprocess

BUFFER_FILE = '/data/night_buffer.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT_LOG = '5340000158'  # личка для логов

def tg_log(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT_LOG, 'text': msg[:1000]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def msk_hour():
    utc = datetime.datetime.utcnow()
    msk = utc + datetime.timedelta(hours=3)
    return msk.hour, msk.minute, msk.weekday()  # weekday: 0=пн, 6=вс

def is_working_time():
    h, m, _ = msk_hour()
    return 8 <= h < 21

def is_morning_trigger():
    """Ровно 08:00–08:09 МСК — утренняя публикация буфера"""
    h, m, _ = msk_hour()
    return h == 8 and m < 10

def load_buffer():
    try:
        with open(BUFFER_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_buffer(items):
    os.makedirs('/data', exist_ok=True)
    with open(BUFFER_FILE, 'w') as f:
        json.dump(items, f, ensure_ascii=False)

def send_to_n8n(channel, html):
    """Отправляем в n8n webhook"""
    payload = json.dumps({'channel': channel, 'html': html}).encode('utf-8')
    try:
        req = urllib.request.Request(
            'http://localhost:5678/webhook/telegram-parser',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception as e:
        print(f"n8n error for {channel}: {e}")
        return False

def parse_channel(channel):
    """Парсим один Telegram канал"""
    import urllib.request as ur
    try:
        req = ur.Request(
            f'https://t.me/s/{channel}',
            headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip, deflate'},
        )
        with ur.urlopen(req, timeout=20) as r:
            data = r.read()
            try:
                import gzip
                html = gzip.decompress(data).decode('utf-8', errors='replace')
            except:
                html = data.decode('utf-8', errors='replace')
        return html
    except Exception as e:
        print(f"Parse error {channel}: {e}")
        return None

CHANNELS = [
    'CRERussia', 'officenewsdaily', 'nedvirf', 'arendator_ru',
    'pravonadom1', 'rusipoteka', 'ria_realty', 'Commers_Estate'
]

h, m, wd = msk_hour()
weekday_name = ['пн','вт','ср','чт','пт','сб','вс'][wd]
working = is_working_time()
morning = is_morning_trigger()

print(f"Time: {h:02d}:{m:02d} MSK ({weekday_name}) | working={working} | morning={morning}")

# === УТРЕННЯЯ ПУБЛИКАЦИЯ БУФЕРА (08:00–08:09 МСК) ===
if morning:
    buffer = load_buffer()
    if buffer:
        print(f"Morning: publishing {len(buffer)} buffered items...")
        published = 0
        for item in buffer:
            if send_to_n8n(item['channel'], item['html']):
                published += 1
                import time; time.sleep(3)
        save_buffer([])  # очищаем буфер
        tg_log(f"🌅 Утренняя публикация: {published} новостей из ночного буфера отправлено в n8n")
        print(f"Published {published} buffered items, buffer cleared")
    else:
        print("Morning: buffer is empty")

# === ПАРСИНГ КАНАЛОВ ===
print(f"\nParsing {len(CHANNELS)} channels...")
parsed = 0
buffered = 0
night_buffer = load_buffer() if not working else []

for channel in CHANNELS:
    print(f"  {channel}...", end=' ')
    html = parse_channel(channel)
    if not html:
        print("FAIL")
        continue

    if working:
        # Рабочее время — сразу в n8n
        if send_to_n8n(channel, html):
            parsed += 1
            print(f"→ n8n OK")
        else:
            print(f"→ n8n FAIL")
        import time; time.sleep(3)
    else:
        # Нерабочее время — в буфер
        night_buffer.append({'channel': channel, 'html': html, 'ts': str(datetime.datetime.utcnow())})
        buffered += 1
        print(f"→ буфер (ночь)")

if not working and buffered > 0:
    save_buffer(night_buffer)
    print(f"\nBuffered {buffered} channels for morning publication")
    # Логируем только раз в час чтобы не спамить
    if m < 31:
        tg_log(f"🌙 Ночной буфер: добавлено {buffered} каналов. В буфере {len(night_buffer)} записей. Публикация в 08:00 МСК.")

if working:
    print(f"\nDone: {parsed}/{len(CHANNELS)} channels sent to n8n")

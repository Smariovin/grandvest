#!/usr/bin/env python3
"""
Grandvest Scheduler v3
- Парсит Telegram каналы каждые 60 мин
- 08:00-21:00 МСК: публикует сразу
- 21:01-07:59 МСК: складывает в буфер
- 08:00-08:14 МСК: публикует буфер
- После публикации: шлёт отчёт в личку
"""
import json, os, datetime, urllib.request, urllib.parse, time, gzip, re

BUFFER_FILE = '/data/night_buffer.json'
LOG_FILE = '/data/published_log.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
PARSER_NAME = 'Парсер Telegram'

CHANNELS = [
    'CRERussia', 'officenewsdaily', 'nedvirf', 'arendator_ru',
    'pravonadom1', 'rusipoteka', 'ria_realty', 'Commers_Estate'
]

def now_msk():
    utc = datetime.datetime.now(datetime.timezone.utc)
    return utc + datetime.timedelta(hours=3)

def tg(msg, chat=MY_CHAT):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat, 'text': str(msg)[:4000], 'parse_mode': 'HTML', 'disable_web_page_preview': True}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def log_publication(entry):
    """Логируем публикацию для отчёта"""
    logs = []
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f: logs = json.load(f)
    except: pass
    logs.append(entry)
    if len(logs) > 200: logs = logs[-150:]
    os.makedirs('/data', exist_ok=True)
    with open(LOG_FILE, 'w') as f: json.dump(logs, f, ensure_ascii=False, indent=2)

def is_work_time(msk_dt):
    """08:00–20:59 МСК — рабочее время"""
    return 8 <= msk_dt.hour < 21

def is_morning_flush(msk_dt):
    """08:00–08:29 МСК — утренний сброс буфера"""
    return msk_dt.hour == 8 and msk_dt.minute < 30

def load_buffer():
    try:
        with open(BUFFER_FILE, 'r') as f: return json.load(f)
    except: return []

def save_buffer(items):
    os.makedirs('/data', exist_ok=True)
    with open(BUFFER_FILE, 'w') as f: json.dump(items, f, ensure_ascii=False)

def get_channel_url(channel):
    return f'https://t.me/s/{channel}'

def parse_channel(channel):
    try:
        req = urllib.request.Request(
            f'https://t.me/s/{channel}',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Encoding': 'gzip, deflate',
                'Accept': 'text/html,application/xhtml+xml'
            }
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try: html = gzip.decompress(raw).decode('utf-8', errors='replace')
            except: html = raw.decode('utf-8', errors='replace')
        
        # Извлекаем последний пост для логирования
        post_match = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        last_post_preview = ''
        if post_match:
            last_post_preview = re.sub(r'<[^>]+>', '', post_match.group(1))[:80].strip()
        
        return html if len(html) > 500 else None, last_post_preview
    except Exception as e:
        return None, ''

def send_to_n8n(channel, html):
    payload = json.dumps({'channel': channel, 'html': html}, ensure_ascii=False).encode('utf-8')
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
        print(f'  n8n error: {e}')
        return False

def notify_published(channel, post_preview, msk_time, buffered=False):
    """Уведомление о публикации в личку"""
    channel_url = f'https://t.me/{channel}'
    status = '🌙 Из ночного буфера' if buffered else '📢 Опубликовано сразу'
    msg = (
        f'📰 <b>Новость отправлена в обработку</b>\n\n'
        f'⏰ Время: {msk_time} МСК\n'
        f'📡 Парсер: {PARSER_NAME}\n'
        f'📌 Канал-источник: <a href="{channel_url}">@{channel}</a>\n'
        f'🔄 Статус: {status}\n'
        f'💬 Превью: {post_preview[:100] if post_preview else "—"}'
    )
    tg(msg)

# ═══════════════════════════════════════
msk = now_msk()
work_time = is_work_time(msk)
morning = is_morning_flush(msk)

print(f"=== Scheduler v3 | {msk.strftime('%d.%m.%Y %H:%M')} МСК ===")
print(f"Режим: {'ПУБЛИКАЦИЯ' if work_time else 'БУФЕР'} | Утро: {morning}")

# ШАГ 1: Утренний сброс буфера 08:00-08:29
if morning:
    buffer = load_buffer()
    if buffer:
        print(f"\n🌅 Утренний сброс: {len(buffer)} записей")
        ok = 0
        for item in buffer:
            ch = item.get('channel', '?')
            html = item.get('html', '')
            preview = item.get('preview', '')
            buf_time = item.get('ts', '?')
            if html and send_to_n8n(ch, html):
                ok += 1
                print(f"  ✓ @{ch}")
                notify_published(ch, preview, msk.strftime('%H:%M'), buffered=True)
                log_publication({
                    'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                    'channel': ch,
                    'channel_url': f'https://t.me/{ch}',
                    'parser': PARSER_NAME,
                    'status': 'from_buffer',
                    'buffered_at': buf_time,
                    'preview': preview[:100]
                })
                time.sleep(5)
        save_buffer([])
        tg(f'🌅 <b>Утренний сброс завершён</b>\nОпубликовано: {ok}/{len(buffer)} каналов')
    else:
        print("Буфер пуст")

# ШАГ 2: Парсинг каналов
print(f"\n📡 Парсинг {len(CHANNELS)} каналов...")
night_buffer = load_buffer() if not work_time else []
published = 0
buffered_count = 0

for channel in CHANNELS:
    print(f"  @{channel}...", end=' ', flush=True)
    html, preview = parse_channel(channel)
    if not html:
        print("FAIL")
        continue

    if work_time:
        if send_to_n8n(channel, html):
            print(f"→ опубликовано ✓")
            published += 1
            notify_published(channel, preview, msk.strftime('%H:%M'), buffered=False)
            log_publication({
                'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                'channel': channel,
                'channel_url': f'https://t.me/{channel}',
                'parser': PARSER_NAME,
                'status': 'published',
                'preview': preview[:100]
            })
        else:
            print("→ FAIL")
        time.sleep(4)
    else:
        night_buffer = [x for x in night_buffer if x.get('channel') != channel]
        night_buffer.append({
            'channel': channel,
            'html': html,
            'preview': preview,
            'ts': msk.strftime('%d.%m.%Y %H:%M МСК')
        })
        print(f"→ буфер")
        buffered_count += 1

if not work_time:
    save_buffer(night_buffer)
    if msk.minute < 30:
        tg(f'🌙 <b>Ночной буфер</b> {msk.strftime("%H:%M")} МСК\n'
           f'Добавлено: {buffered_count} каналов\n'
           f'Всего в буфере: {len(night_buffer)}\n'
           f'Публикация в 08:00 МСК')
else:
    print(f"\n✅ Опубликовано: {published}/{len(CHANNELS)}")

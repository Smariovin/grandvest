#!/usr/bin/env python3
"""
Grandvest Smart Scheduler v2
Расписание: публикация 08:00-21:00 МСК, 7 дней в неделю
Ночью 21:01-07:59 — парсим в буфер, публикуем в 08:00
"""
import json, os, datetime, urllib.request, urllib.parse, time, gzip

BUFFER_FILE = '/data/night_buffer.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'

CHANNELS = [
    'CRERussia', 'officenewsdaily', 'nedvirf', 'arendator_ru',
    'pravonadom1', 'rusipoteka', 'ria_realty', 'Commers_Estate'
]

def now_msk():
    utc = datetime.datetime.now(datetime.timezone.utc)
    msk = utc + datetime.timedelta(hours=3)
    return msk

def tg_log(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': MY_CHAT,
        'text': msg[:1000],
        'parse_mode': 'HTML'
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e:
        print(f'TG log error: {e}')

def is_publish_time(msk_dt):
    """08:00–21:00 МСК — рабочее время, публикуем сразу"""
    return 8 <= msk_dt.hour < 21

def is_morning_flush(msk_dt):
    """08:00–08:14 МСК — утренний сброс ночного буфера"""
    return msk_dt.hour == 8 and msk_dt.minute < 15

def load_buffer():
    try:
        with open(BUFFER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_buffer(items):
    os.makedirs('/data', exist_ok=True)
    with open(BUFFER_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)

def send_to_n8n(channel, html):
    payload = json.dumps(
        {'channel': channel, 'html': html},
        ensure_ascii=False
    ).encode('utf-8')
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
            try:
                html = gzip.decompress(raw).decode('utf-8', errors='replace')
            except:
                html = raw.decode('utf-8', errors='replace')
        return html if len(html) > 500 else None
    except Exception as e:
        print(f'  parse error: {e}')
        return None

# ─────────────────────────────────────────────
msk = now_msk()
weekday = ['пн','вт','ср','чт','пт','сб','вс'][msk.weekday()]
publish_mode = is_publish_time(msk)
morning_flush = is_morning_flush(msk)

print(f"=== Grandvest Scheduler v2 ===")
print(f"MSK: {msk.strftime('%d.%m.%Y %H:%M')} ({weekday})")
print(f"Режим: {'📢 ПУБЛИКАЦИЯ' if publish_mode else '🌙 НОЧНОЙ БУФЕР'}")
print(f"Утренний сброс: {'ДА' if morning_flush else 'нет'}")

# ─────────────────────────────────────────────
# ШАГ 1: Утренний сброс буфера (08:00–08:14 МСК)
# ─────────────────────────────────────────────
if morning_flush:
    buffer = load_buffer()
    if buffer:
        print(f"\n🌅 Утренний сброс: {len(buffer)} записей в буфере")
        ok = 0
        for item in buffer:
            ch = item.get('channel', '?')
            html = item.get('html', '')
            if html and send_to_n8n(ch, html):
                ok += 1
                print(f"  ✓ {ch}")
                time.sleep(4)
            else:
                print(f"  ✗ {ch}")
        save_buffer([])
        print(f"Буфер очищен. Опубликовано: {ok}/{len(buffer)}")
        tg_log(
            f"🌅 <b>Утренний запуск 08:00</b>\n"
            f"Ночной буфер: {ok} из {len(buffer)} каналов отправлено в n8n\n"
            f"Буфер очищен ✅"
        )
    else:
        print("\n🌅 Утренний сброс: буфер пуст")

# ─────────────────────────────────────────────
# ШАГ 2: Парсинг каналов
# ─────────────────────────────────────────────
print(f"\n📡 Парсинг {len(CHANNELS)} каналов...")

night_buffer = load_buffer() if not publish_mode else []
parsed_ok = 0
buffered = 0

for channel in CHANNELS:
    print(f"  {channel}...", end=' ', flush=True)
    html = parse_channel(channel)

    if not html:
        print("FAIL — пропуск")
        continue

    if publish_mode:
        # Рабочее время — сразу в n8n
        if send_to_n8n(channel, html):
            print("→ n8n ✓")
            parsed_ok += 1
        else:
            print("→ n8n FAIL")
        time.sleep(3)
    else:
        # Ночное время — в буфер (перезаписываем, берём свежий HTML)
        # Убираем старую запись этого канала если есть
        night_buffer = [x for x in night_buffer if x.get('channel') != channel]
        night_buffer.append({
            'channel': channel,
            'html': html,
            'ts': msk.strftime('%Y-%m-%d %H:%M MSK')
        })
        print(f"→ буфер ✓")
        buffered += 1

# Сохраняем ночной буфер
if not publish_mode:
    save_buffer(night_buffer)
    total_in_buffer = len(night_buffer)
    print(f"\n💾 Буфер сохранён: {total_in_buffer} каналов")
    # Логируем только в начале каждого часа чтобы не спамить
    if msk.minute < 31:
        tg_log(
            f"🌙 <b>Ночной буфер</b> {msk.strftime('%H:%M')} МСК\n"
            f"Добавлено: {buffered} каналов\n"
            f"Всего в буфере: {total_in_buffer}\n"
            f"Публикация в 08:00 МСК"
        )
else:
    print(f"\n✅ Готово: {parsed_ok}/{len(CHANNELS)} каналов отправлено в n8n")

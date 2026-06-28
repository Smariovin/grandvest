#!/usr/bin/env python3
"""
Grandvest Scheduler v4
Логика:
- Запускается каждые 60 мин (cron: 0 * * * *)
- 08:01-21:00 МСК: парсит новости за ПОСЛЕДНИЙ ЧАС → публикует сразу
- 21:01-07:59 МСК: парсит → в ночной буфер
- 08:00-08:14 МСК: публикует ночной буфер → затем парсит текущий час
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
    data = urllib.parse.urlencode({
        'chat_id': chat, 'text': str(msg)[:4000],
        'parse_mode': 'HTML', 'disable_web_page_preview': True
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def log_pub(entry):
    logs = []
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f: logs = json.load(f)
    except: pass
    logs.append(entry)
    if len(logs) > 500: logs = logs[-300:]
    os.makedirs('/data', exist_ok=True)
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def load_buffer():
    try:
        with open(BUFFER_FILE) as f: return json.load(f)
    except: return []

def save_buffer(items):
    os.makedirs('/data', exist_ok=True)
    with open(BUFFER_FILE, 'w') as f:
        json.dump(items, f, ensure_ascii=False)

def parse_channel(channel, from_dt, to_dt):
    """
    Парсит канал и фильтрует посты за период from_dt..to_dt (объекты datetime MSK)
    Возвращает (html_страницы, список постов за период, превью последнего)
    """
    try:
        req = urllib.request.Request(
            f'https://t.me/s/{channel}',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept-Encoding': 'gzip, deflate',
                'Accept': 'text/html,application/xhtml+xml'
            }
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try: html = gzip.decompress(raw).decode('utf-8', errors='replace')
            except: html = raw.decode('utf-8', errors='replace')

        if len(html) < 500:
            return None, [], ''

        # Извлекаем посты с временем из <time datetime="...">
        posts = []
        # Ищем блоки сообщений
        msg_blocks = re.findall(
            r'<div class="tgme_widget_message_wrap[^"]*".*?</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )

        for block in msg_blocks:
            # Время поста
            time_match = re.search(r'<time[^>]+datetime="([^"]+)"', block)
            if not time_match:
                continue
            try:
                dt_str = time_match.group(1)  # e.g. 2026-06-28T07:30:00+00:00
                post_utc = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                post_msk = post_utc + datetime.timedelta(hours=3)
            except:
                continue

            # Фильтр по времени
            if from_dt <= post_msk <= to_dt:
                text_match = re.search(
                    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                    block, re.DOTALL
                )
                text = ''
                if text_match:
                    text = re.sub(r'<[^>]+>', '', text_match.group(1)).strip()[:200]
                posts.append({
                    'time_msk': post_msk.strftime('%H:%M'),
                    'text': text
                })

        preview = posts[-1]['text'][:80] if posts else ''
        return html, posts, preview

    except Exception as e:
        print(f'  parse error {channel}: {e}')
        return None, [], ''

def send_to_n8n(channel, html):
    payload = json.dumps(
        {'channel': channel, 'html': html}, ensure_ascii=False
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

def notify(channel, posts_count, period_str, msk_now, buffered=False):
    status = '🌙 В ночной буфер' if buffered else '📢 Опубликовано сразу'
    tg(
        f'📰 <b>{"Буфер" if buffered else "Публикация"} | {PARSER_NAME}</b>\n\n'
        f'📌 @{channel}\n'
        f'⏰ Время: {msk_now.strftime("%H:%M")} МСК\n'
        f'📅 Период новостей: {period_str}\n'
        f'📊 Постов за период: {posts_count}\n'
        f'🔄 {status}'
    )

# ═══════════════════════════════
msk = now_msk()
h = msk.hour
m = msk.minute

print(f"=== Scheduler v4 | {msk.strftime('%d.%m.%Y %H:%M')} МСК ===")

# Определяем период для парсинга (последний час)
# Если сейчас 10:05 — берём посты с 09:01 по 10:00
period_to = msk.replace(minute=0, second=0, microsecond=0)
period_from = period_to - datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)
period_str = f'{period_from.strftime("%H:%M")}–{period_to.strftime("%H:%M")}'
print(f"Период парсинга: {period_str} МСК")

# Режимы
IS_WORK = 8 <= h < 21  # 08:00-20:59 → публикуем
IS_MORNING = h == 8 and m < 15  # 08:00-08:14 → сброс буфера

print(f"Режим: {'РАБОТА' if IS_WORK else 'НОЧЬ'} | Утренний сброс: {IS_MORNING}")

# ─── ШАГ 1: Утренний сброс буфера ───
if IS_MORNING:
    buffer = load_buffer()
    if buffer:
        print(f"\n🌅 Утренний сброс: {len(buffer)} каналов")
        ok = 0
        for item in buffer:
            ch = item.get('channel', '?')
            html = item.get('html', '')
            posts_count = item.get('posts_count', 0)
            buf_period = item.get('period', '?')
            buf_time = item.get('ts', '?')

            if html and send_to_n8n(ch, html):
                ok += 1
                print(f"  ✓ @{ch}")
                log_pub({
                    'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                    'channel': ch,
                    'channel_url': f'https://t.me/{ch}',
                    'parser': PARSER_NAME,
                    'status': 'published_from_buffer',
                    'period': buf_period,
                    'buffered_at': buf_time,
                    'posts_count': posts_count
                })
                tg(
                    f'🌅 <b>Из ночного буфера</b>\n\n'
                    f'📌 @{ch}\n'
                    f'⏰ Публикация: 08:01 МСК\n'
                    f'📅 Новости за: {buf_period}\n'
                    f'📊 Постов: {posts_count}\n'
                    f'🔗 https://t.me/{ch}'
                )
                time.sleep(5)

        save_buffer([])
        tg(
            f'🌅 <b>Утренний сброс завершён</b>\n'
            f'Опубликовано: {ok}/{len(buffer)} каналов\n'
            f'Новости за период 21:01–08:00 МСК'
        )
    else:
        print("Буфер пуст")

# ─── ШАГ 2: Парсинг каналов ───
print(f"\n📡 Парсинг {len(CHANNELS)} каналов за {period_str}...")

night_buffer = load_buffer() if not IS_WORK else []
total_published = 0
total_buffered = 0
total_no_news = 0
channel_report = []

for channel in CHANNELS:
    print(f"  @{channel}...", end=' ', flush=True)

    html, posts, preview = parse_channel(channel, period_from, period_to)

    if html is None:
        print("FAIL — недоступен")
        channel_report.append(f'❌ @{channel}: недоступен')
        continue

    posts_count = len(posts)
    print(f"{posts_count} постов за период", end=' ')

    if posts_count == 0:
        print("→ нет новых постов")
        channel_report.append(f'⚪ @{channel}: нет постов за {period_str}')
        total_no_news += 1
        continue

    if IS_WORK:
        # Рабочее время — публикуем сразу
        if send_to_n8n(channel, html):
            print("→ опубликовано ✓")
            total_published += 1
            channel_report.append(
                f'✅ @{channel}: {posts_count} постов → опубликовано'
            )
            log_pub({
                'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                'channel': channel,
                'channel_url': f'https://t.me/{channel}',
                'parser': PARSER_NAME,
                'status': 'published',
                'period': period_str,
                'posts_count': posts_count,
                'preview': preview[:100]
            })
            tg(
                f'📢 <b>Новость опубликована</b>\n\n'
                f'📡 Парсер: {PARSER_NAME}\n'
                f'📌 Источник: @{channel}\n'
                f'🔗 https://t.me/{channel}\n'
                f'⏰ Время: {msk.strftime("%H:%M")} МСК\n'
                f'📅 Новости за: {period_str}\n'
                f'📊 Постов найдено: {posts_count}\n'
                f'💬 {preview[:80]}'
            )
        else:
            print("→ FAIL")
            channel_report.append(f'⚠️ @{channel}: ошибка отправки в n8n')
        time.sleep(4)
    else:
        # Ночное время — в буфер
        night_buffer = [x for x in night_buffer if x.get('channel') != channel]
        night_buffer.append({
            'channel': channel,
            'html': html,
            'preview': preview,
            'period': period_str,
            'posts_count': posts_count,
            'ts': msk.strftime('%d.%m.%Y %H:%M МСК')
        })
        print("→ в буфер")
        total_buffered += 1
        channel_report.append(
            f'🌙 @{channel}: {posts_count} постов → буфер'
        )

# Сохраняем буфер
if not IS_WORK:
    save_buffer(night_buffer)

# ─── Итоговый отчёт часа ───
report = [
    f'📊 <b>Отчёт парсинга {period_str} МСК</b>',
    f'📅 {msk.strftime("%d.%m.%Y")} | {PARSER_NAME}',
    ''
]

if IS_WORK:
    report.append(f'✅ Опубликовано: {total_published}')
else:
    report.append(f'🌙 В буфер: {total_buffered}')

report.append(f'⚪ Без новостей: {total_no_news}')
report.append(f'❌ Ошибки: {len(CHANNELS)-total_published-total_buffered-total_no_news}')
report.append('')
report.append('<b>По каналам:</b>')
report.extend(channel_report)

tg('\n'.join(report))
print(f"\nГотово: опубликовано={total_published} буфер={total_buffered} пусто={total_no_news}")

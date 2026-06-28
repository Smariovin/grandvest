#!/usr/bin/env python3
"""
Grandvest Scheduler v5
Исправление: отправляем в n8n только последний пост за период,
а не всю HTML страницу канала
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

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': MY_CHAT, 'text': str(msg)[:4000],
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
    Возвращает список постов за период from_dt..to_dt
    Каждый пост: {'html': '<div class=tgme_widget_message_text...>', 'time': ..., 'text': ...}
    """
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
            try: page = gzip.decompress(raw).decode('utf-8', errors='replace')
            except: page = raw.decode('utf-8', errors='replace')

        if len(page) < 500:
            return []

        # Ищем блоки сообщений с временными метками
        # Формат: <div class="tgme_widget_message ...">...<time datetime="2026-06-28T...">
        posts = []

        # Разбиваем на отдельные сообщения
        msg_pattern = re.compile(
            r'(<div class="tgme_widget_message_wrap[^>]*>.*?</div>\s*</div>\s*</div>)',
            re.DOTALL
        )

        for block in msg_pattern.finditer(page):
            block_html = block.group(1)

            # Время поста
            time_m = re.search(r'<time[^>]+datetime="([^"]+)"', block_html)
            if not time_m:
                continue
            try:
                dt_raw = time_m.group(1)
                post_utc = datetime.datetime.fromisoformat(dt_raw.replace('Z', '+00:00'))
                post_msk = post_utc + datetime.timedelta(hours=3)
            except:
                continue

            # Фильтр по временному окну
            if not (from_dt <= post_msk <= to_dt):
                continue

            # Извлекаем div с текстом поста
            text_div_m = re.search(
                r'(<div class="tgme_widget_message_text[^"]*"[^>]*>.*?</div>)',
                block_html, re.DOTALL
            )
            if not text_div_m:
                continue

            text_div = text_div_m.group(1)
            text_clean = re.sub(r'<[^>]+>', '', text_div).strip()

            if len(text_clean) < 20:  # Слишком короткое сообщение
                continue

            # Ссылка на пост
            link_m = re.search(r'href="(https://t\.me/[^"]+)"', block_html)
            post_url = link_m.group(1) if link_m else f'https://t.me/{channel}'

            posts.append({
                'text_div': text_div,
                'text': text_clean[:300],
                'time_msk': post_msk.strftime('%H:%M'),
                'post_url': post_url,
                'channel': channel,
                'channel_url': f'https://t.me/{channel}'
            })

        return posts

    except Exception as e:
        print(f'  parse error @{channel}: {e}')
        return []

def send_post_to_n8n(channel, post):
    """
    Отправляем ОДИН пост в n8n вебхук в правильном формате
    Формат: {channel, html} - где html это только div с текстом поста + time тег
    """
    # Формируем HTML в том формате который ожидает узел 1
    time_str = post['time_msk']
    html_payload = (
        f'<div class="tgme_widget_message_text js-message_text">'
        f'{post["text"]}'
        f'</div>'
        f'<time datetime="2026-06-28T{time_str}:00+00:00">{time_str}</time>'
    )

    payload = json.dumps({
        'channel': channel,
        'html': html_payload,
        'source_url': post.get('post_url', f'https://t.me/{channel}'),
        'channel_url': post.get('channel_url', f'https://t.me/{channel}')
    }, ensure_ascii=False).encode('utf-8')

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

# ═══════════════════════════════
msk = now_msk()
h = msk.hour
m = msk.minute

print(f"=== Scheduler v5 | {msk.strftime('%d.%m.%Y %H:%M')} МСК ===")

# Период парсинга: последний час
period_to = msk.replace(minute=0, second=0, microsecond=0)
period_from = period_to - datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)
period_str = f'{period_from.strftime("%H:%M")}–{period_to.strftime("%H:%M")}'
print(f"Период: {period_str} МСК")

IS_WORK = 8 <= h < 21
IS_MORNING = h == 8 and m < 15

print(f"Режим: {'ПУБЛИКАЦИЯ' if IS_WORK else 'НОЧЬ'} | Утро: {IS_MORNING}")

# ─── Утренний сброс буфера ───
if IS_MORNING:
    buffer = load_buffer()
    if buffer:
        print(f"\n🌅 Утренний сброс: {len(buffer)} постов")
        ok = 0
        for item in buffer:
            ch = item.get('channel', '?')
            if send_post_to_n8n(ch, item):
                ok += 1
                print(f"  ✓ @{ch} [{item.get('time_msk','?')}]")
                time.sleep(5)
        save_buffer([])
        tg(f'🌅 <b>Утренний сброс</b>\nОпубликовано: {ok}/{len(buffer)} постов\n'
           f'Период: 21:01–08:00 МСК')
    else:
        print("Буфер пуст")

# ─── Парсинг каналов ───
print(f"\n📡 Парсинг {len(CHANNELS)} каналов за {period_str}...")

night_buffer = load_buffer() if not IS_WORK else []
published = 0
buffered = 0
no_news = 0
channel_report = []

for channel in CHANNELS:
    print(f"  @{channel}...", end=' ', flush=True)
    posts = parse_channel(channel, period_from, period_to)

    if posts is None or (isinstance(posts, list) and len(posts) == 0):
        print(f"нет постов за {period_str}")
        channel_report.append(f'⚪ @{channel}: нет новых постов за {period_str}')
        no_news += 1
        continue

    # Берём последний пост за период
    post = posts[-1]
    print(f"{len(posts)} пост(ов) → берём последний [{post['time_msk']}]")

    if IS_WORK:
        if send_post_to_n8n(channel, post):
            published += 1
            channel_report.append(
                f'✅ @{channel}: опубликован пост {post["time_msk"]} МСК\n'
                f'   💬 {post["text"][:60]}...'
            )
            log_pub({
                'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                'channel': channel,
                'channel_url': f'https://t.me/{channel}',
                'post_url': post.get('post_url',''),
                'parser': PARSER_NAME,
                'status': 'published',
                'period': period_str,
                'posts_count': len(posts),
                'preview': post['text'][:100]
            })
            # Уведомление — новость отправлена в обработку
            tg(
                f'📰 <b>Новость отправлена в обработку</b>\n\n'
                f'📡 Парсер: {PARSER_NAME}\n'
                f'📌 Источник: <a href="https://t.me/{channel}">@{channel}</a>\n'
                f'🔗 Пост: <a href="{post.get("post_url", f"https://t.me/{channel}")}">открыть</a>\n'
                f'⏰ Время новости: {post["time_msk"]} МСК\n'
                f'📅 Период: {period_str}\n'
                f'💬 {post["text"][:80]}...'
            )
        else:
            channel_report.append(f'⚠️ @{channel}: ошибка n8n')
        time.sleep(4)
    else:
        # Ночной буфер — убираем старую запись канала
        night_buffer = [x for x in night_buffer if x.get('channel') != channel]
        night_buffer.append({**post, 'channel': channel, 'period': period_str,
                              'ts': msk.strftime('%d.%m.%Y %H:%M МСК')})
        buffered += 1
        channel_report.append(f'🌙 @{channel}: {len(posts)} постов → буфер')

if not IS_WORK:
    save_buffer(night_buffer)

# ─── Итоговый почасовой отчёт ───
report = [
    f'📊 <b>Отчёт парсинга {period_str} МСК</b>',
    f'🗓 {msk.strftime("%d.%m.%Y")} | {PARSER_NAME}', ''
]
if IS_WORK:
    report.append(f'✅ Отправлено в публикацию: {published}')
else:
    report.append(f'🌙 В ночной буфер: {buffered}')
report.append(f'⚪ Без новостей за период: {no_news}')
report.append('')
report.append('<b>По каналам:</b>')
report.extend(channel_report)
tg('\n'.join(report))
print(f"Готово: published={published} buffered={buffered} no_news={no_news}")

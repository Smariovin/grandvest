#!/usr/bin/env python3
"""
Grandvest Scheduler v6
Детальный почасовой отчёт по парсингу Telegram каналов
"""
import json, os, datetime, urllib.request, urllib.parse, time, gzip, re

BUFFER_FILE = '/data/night_buffer.json'
LOG_FILE = '/data/published_log.json'
REPORT_FILE = '/data/hourly_report.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
PARSER_NAME = 'Парсер Telegram'

CHANNELS = [
    'CRERussia', 'officenewsdaily', 'nedvirf', 'arendator_ru',
    'pravonadom1', 'rusipoteka', 'ria_realty', 'Commers_Estate'
]

def now_msk():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': MY_CHAT, 'text': str(msg)[:4000],
        'parse_mode': 'HTML', 'disable_web_page_preview': True
    }).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def load_buffer():
    try:
        with open(BUFFER_FILE) as f: return json.load(f)
    except: return []

def save_buffer(items):
    os.makedirs('/data', exist_ok=True)
    with open(BUFFER_FILE, 'w') as f: json.dump(items, f, ensure_ascii=False)

def log_pub(entry):
    logs = []
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f: logs = json.load(f)
    except: pass
    logs.append(entry)
    if len(logs) > 500: logs = logs[-300:]
    os.makedirs('/data', exist_ok=True)
    with open(LOG_FILE, 'w') as f: json.dump(logs, f, ensure_ascii=False, indent=2)

def parse_channel(channel, from_dt, to_dt):
    try:
        req = urllib.request.Request(
            f'https://t.me/s/{channel}',
            headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip, deflate'}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try: page = gzip.decompress(raw).decode('utf-8', errors='replace')
            except: page = raw.decode('utf-8', errors='replace')
        if len(page) < 500: return [], 0
        
        # Считаем ВСЕ посты на странице (за последние дни)
        all_times = re.findall(r'<time[^>]+datetime="([^"]+)"', page)
        total_on_page = len(all_times)
        
        # Посты за наш период
        posts_in_period = []
        msg_blocks = re.findall(
            r'<div class="tgme_widget_message_wrap[^>]*>.*?</div>\s*</div>\s*</div>',
            page, re.DOTALL
        )
        for block in msg_blocks:
            time_m = re.search(r'<time[^>]+datetime="([^"]+)"', block)
            if not time_m: continue
            try:
                post_utc = datetime.datetime.fromisoformat(time_m.group(1).replace('Z','+00:00'))
                post_msk = post_utc + datetime.timedelta(hours=3)
            except: continue
            if not (from_dt <= post_msk <= to_dt): continue
            text_m = re.search(
                r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                block, re.DOTALL
            )
            if not text_m: continue
            text = re.sub(r'<[^>]+>', '', text_m.group(1)).strip()
            if len(text) < 20: continue
            link_m = re.search(r'href="(https://t\.me/[^"]+)"', block)
            posts_in_period.append({
                'text': text[:300],
                'time_msk': post_msk.strftime('%H:%M'),
                'post_url': link_m.group(1) if link_m else f'https://t.me/{channel}',
                'channel': channel,
                'channel_url': f'https://t.me/{channel}'
            })
        return posts_in_period, total_on_page
    except Exception as e:
        print(f'  parse error @{channel}: {e}')
        return None, 0  # None = ошибка доступа

def send_post_to_n8n(channel, post):
    html = (
        f'<div class="tgme_widget_message_text js-message_text">{post["text"]}</div>'
        f'<time datetime="2026-06-28T{post["time_msk"]}:00+00:00">{post["time_msk"]}</time>'
    )
    payload = json.dumps({
        'channel': channel, 'html': html,
        'source_url': post.get('post_url', f'https://t.me/{channel}'),
        'channel_url': post.get('channel_url', f'https://t.me/{channel}')
    }, ensure_ascii=False).encode('utf-8')
    try:
        urllib.request.urlopen(urllib.request.Request(
            'http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type': 'application/json'}
        ), timeout=30)
        return True
    except Exception as e:
        print(f'  n8n error: {e}')
        return False

# ═══════════════════════════════
msk = now_msk()
h, m = msk.hour, msk.minute
period_to = msk.replace(minute=0, second=0, microsecond=0)
period_from = period_to - datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)
period_str = f'{period_from.strftime("%H:%M")}–{period_to.strftime("%H:%M")}'
IS_WORK = 8 <= h < 21
IS_MORNING = h == 8 and m < 15

print(f"=== Scheduler v6 | {msk.strftime('%d.%m.%Y %H:%M')} МСК | {period_str} ===")

# ─── Утренний сброс ───
if IS_MORNING:
    buffer = load_buffer()
    if buffer:
        ok = 0
        for item in buffer:
            ch = item.get('channel','?')
            if send_post_to_n8n(ch, item):
                ok += 1
                time.sleep(5)
        save_buffer([])
        tg(f'🌅 <b>Утренний сброс</b>\nОпубликовано: {ok}/{len(buffer)} постов\nНовости за: 21:01–08:00 МСК')

# ─── Парсинг каналов + сбор статистики ───
night_buffer = load_buffer() if not IS_WORK else []

stats = {
    'period': period_str,
    'date': msk.strftime('%d.%m.%Y'),
    'time': msk.strftime('%H:%M'),
    'channels': []
}

total_parsed = 0
total_period = 0
total_sent = 0
total_buffered = 0
total_errors = 0

for channel in CHANNELS:
    print(f"  @{channel}...", end=' ', flush=True)
    posts, total_on_page = parse_channel(channel, period_from, period_to)
    
    ch_stat = {
        'channel': channel,
        'url': f'https://t.me/{channel}',
        'total_on_page': total_on_page,
        'posts_in_period': 0,
        'sent_to_n8n': False,
        'status': ''
    }
    
    if posts is None:
        # Ошибка доступа
        ch_stat['status'] = 'error'
        total_errors += 1
        print("ОШИБКА ДОСТУПА")
    elif len(posts) == 0:
        ch_stat['status'] = 'no_news'
        print(f"нет постов за {period_str} (всего на странице: {total_on_page})")
    else:
        total_parsed += total_on_page
        total_period += len(posts)
        ch_stat['posts_in_period'] = len(posts)
        
        post = posts[-1]  # Берём последний пост
        
        if IS_WORK:
            if send_post_to_n8n(channel, post):
                total_sent += 1
                ch_stat['sent_to_n8n'] = True
                ch_stat['status'] = 'published'
                ch_stat['selected_post_time'] = post['time_msk']
                print(f"{len(posts)} постов → отправлен [{post['time_msk']}] ✓")
                log_pub({
                    'time_msk': msk.strftime('%d.%m.%Y %H:%M'),
                    'channel': channel,
                    'channel_url': f'https://t.me/{channel}',
                    'post_url': post.get('post_url',''),
                    'parser': PARSER_NAME,
                    'status': 'sent_to_n8n',
                    'period': period_str,
                    'posts_count': len(posts),
                    'preview': post['text'][:100]
                })
                tg(
                    f'📰 <b>Новость отправлена в обработку</b>\n\n'
                    f'📡 Парсер: {PARSER_NAME}\n'
                    f'📌 Источник: <a href="https://t.me/{channel}">@{channel}</a>\n'
                    f'⏰ Время новости: {post["time_msk"]} МСК\n'
                    f'📅 Период: {period_str}\n'
                    f'📊 Постов за период: {len(posts)}\n'
                    f'💬 {post["text"][:80]}...'
                )
            else:
                ch_stat['status'] = 'n8n_error'
                print("→ ОШИБКА N8N")
            time.sleep(4)
        else:
            night_buffer = [x for x in night_buffer if x.get('channel') != channel]
            night_buffer.append({**post, 'channel': channel, 'period': period_str,
                                  'ts': msk.strftime('%d.%m.%Y %H:%M МСК')})
            total_buffered += 1
            ch_stat['status'] = 'buffered'
            print(f"{len(posts)} постов → буфер")
    
    stats['channels'].append(ch_stat)

if not IS_WORK:
    save_buffer(night_buffer)

# ─── Детальный почасовой отчёт ───
lines = [
    f'📊 <b>Отчёт парсинга Telegram | {period_str} МСК</b>',
    f'📅 {msk.strftime("%d.%m.%Y")} | {PARSER_NAME}',
    '',
    f'<b>Итого за период:</b>',
    f'📡 Источников проверено: {len(CHANNELS)}',
    f'📰 Новых постов за {period_str}: {total_period}',
    f'✅ Отобрано для публикации: {total_sent if IS_WORK else total_buffered}',
    f'❌ Ошибок доступа: {total_errors}',
    '',
    '<b>По каналам:</b>'
]

for cs in stats['channels']:
    ch = cs['channel']
    status = cs['status']
    n_period = cs['posts_in_period']
    
    if status == 'error':
        lines.append(f'❌ @{ch} — ошибка доступа к каналу')
    elif status == 'no_news':
        lines.append(f'⚪ @{ch} — 0 постов за {period_str}')
    elif status == 'published':
        t = cs.get('selected_post_time','?')
        lines.append(f'✅ @{ch} — найдено {n_period}, отправлен пост [{t}] → в обработку')
    elif status == 'buffered':
        lines.append(f'🌙 @{ch} — найдено {n_period}, добавлен в буфер')
    elif status == 'n8n_error':
        lines.append(f'⚠️ @{ch} — найдено {n_period}, ошибка отправки в n8n')

if not IS_WORK:
    lines.append('')
    lines.append(f'🌙 Ночной режим: {total_buffered} каналов в буфере')
    lines.append(f'Публикация в 08:01 МСК')

tg('\n'.join(lines))
print(f"\nГотово: period={total_period} sent={total_sent} buf={total_buffered} err={total_errors}")

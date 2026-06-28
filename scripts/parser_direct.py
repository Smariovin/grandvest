#!/usr/bin/env python3
"""
Grandvest Parser v7 — запускается прямо на GitHub Actions (США/ЕС)
Не зависит от VPS и российских IP-блокировок
Парсит t.me/s/ напрямую, отправляет в n8n через вебхук
"""
import json, os, datetime, urllib.request, urllib.parse, time, gzip, re

VPS_WEBHOOK = 'http://85.239.61.157:5678/webhook/telegram-parser'
BUFFER_API  = 'http://85.239.61.157:5678/webhook/night-buffer'
BOT    = os.environ.get('BOT_TOKEN', '')
MY_CHAT = '5340000158'
PARSER_NAME = 'Парсер Telegram'
LOG_FILE = '/tmp/parse_log.json'

CHANNELS = [
    'CRERussia', 'officenewsdaily', 'nedvirf', 'arendator_ru',
    'pravonadom1', 'rusipoteka', 'ria_realty', 'Commers_Estate'
]

def now_msk():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

def tg(msg):
    if not BOT: return
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': MY_CHAT, 'text': str(msg)[:4000],
        'parse_mode': 'HTML', 'disable_web_page_preview': True
    }).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e: print(f'TG err: {e}')

def parse_channel(channel, from_dt, to_dt):
    """Парсит с GitHub Actions (внешний IP) — t.me/s/ доступен"""
    errors = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f'https://t.me/s/{channel}',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate',
                    'Cache-Control': 'no-cache'
                }
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                try: page = gzip.decompress(raw).decode('utf-8', errors='replace')
                except: page = raw.decode('utf-8', errors='replace')

            if len(page) < 500:
                errors.append(f'empty response ({len(page)} bytes)')
                time.sleep(2)
                continue

            # Все посты на странице
            all_times = re.findall(r'<time[^>]+datetime="([^"]+)"', page)
            total = len(all_times)

            # Посты за нужный период
            posts = []
            blocks = re.findall(
                r'<div class="tgme_widget_message_wrap[^>]*>.*?(?=<div class="tgme_widget_message_wrap|$)',
                page, re.DOTALL
            )

            for block in blocks:
                time_m = re.search(r'<time[^>]+datetime="([^"]+)"', block)
                if not time_m: continue
                try:
                    post_utc = datetime.datetime.fromisoformat(time_m.group(1).replace('Z','+00:00'))
                    post_msk = post_utc + datetime.timedelta(hours=3)
                except: continue

                if not (from_dt <= post_msk <= to_dt): continue

                text_m = re.search(
                    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                    block, re.DOTALL
                )
                if not text_m: continue
                text = re.sub(r'<[^>]+>', '', text_m.group(1)).strip()
                if len(text) < 20: continue

                link_m = re.search(r'href="(https://t\.me/[^"]+\d+)"', block)
                posts.append({
                    'text': text[:400],
                    'time_msk': post_msk.strftime('%H:%M'),
                    'post_url': link_m.group(1) if link_m else f'https://t.me/{channel}',
                    'channel': channel,
                    'channel_url': f'https://t.me/{channel}'
                })

            return posts, total, None

        except urllib.error.HTTPError as e:
            err = f'HTTP {e.code}'
            errors.append(err)
            if e.code in (403, 404): break
            time.sleep(3)
        except Exception as e:
            errors.append(str(e))
            time.sleep(2)

    return None, 0, ' / '.join(errors)

def send_to_n8n(channel, post):
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
            VPS_WEBHOOK, data=payload,
            headers={'Content-Type': 'application/json'}
        ), timeout=30)
        return True
    except Exception as e:
        print(f'  n8n err: {e}')
        return False

# ═══════════════════════════
msk = now_msk()
h, m = msk.hour, msk.minute
period_to   = msk.replace(minute=0, second=0, microsecond=0)
period_from = period_to - datetime.timedelta(hours=1) + datetime.timedelta(minutes=1)
period_str  = f'{period_from.strftime("%H:%M")}–{period_to.strftime("%H:%M")}'
IS_WORK   = 8 <= h < 21
IS_MORNING = h == 8 and m < 15

print(f"=== Parser v7 | {msk.strftime('%d.%m.%Y %H:%M')} МСК | {period_str} ===")
print(f"Running on GitHub Actions (external IP — no RU blocking)")

# Утренний сброс буфера через VPS API
if IS_MORNING:
    try:
        req = urllib.request.Request(
            f'http://85.239.61.157:5678/webhook/flush-buffer',
            data=b'{}', headers={'Content-Type':'application/json'})
        urllib.request.urlopen(req, timeout=15)
        print("Buffer flush triggered")
    except: pass

# Парсинг
stats = []
total_period = 0
total_sent = 0
total_buf = 0
total_err = 0
total_empty = 0

for channel in CHANNELS:
    print(f"  @{channel}...", end=' ', flush=True)
    posts, total_on_page, error = parse_channel(channel, period_from, period_to)

    if error:
        total_err += 1
        stats.append({'ch': channel, 'status': 'error', 'error': error, 'n': 0, 'total': 0})
        print(f"ERROR: {error}")
        continue

    n = len(posts)
    stats.append({'ch': channel, 'status': 'ok' if n > 0 else 'empty',
                  'n': n, 'total': total_on_page, 'post': posts[-1] if posts else None})

    if n == 0:
        total_empty += 1
        print(f"нет постов за {period_str} (всего на стр: {total_on_page})")
        continue

    total_period += n
    post = posts[-1]
    print(f"{n} постов → [{post['time_msk']}]", end=' ')

    if IS_WORK:
        if send_to_n8n(channel, post):
            total_sent += 1
            stats[-1]['status'] = 'sent'
            print("→ отправлен ✓")
            tg(
                f'📰 <b>Новость отправлена</b>\n\n'
                f'📡 {PARSER_NAME}\n'
                f'📌 <a href="https://t.me/{channel}">@{channel}</a>\n'
                f'⏰ Новость: {post["time_msk"]} МСК\n'
                f'📅 Период: {period_str}\n'
                f'📊 Найдено: {n} постов\n'
                f'🔗 <a href="{post["post_url"]}">Открыть</a>\n'
                f'💬 {post["text"][:80]}...'
            )
        else:
            stats[-1]['status'] = 'n8n_err'
            print("→ n8n ОШИБКА")
        time.sleep(4)
    else:
        total_buf += 1
        stats[-1]['status'] = 'buffered'
        print("→ буфер")

# ─── Итоговый отчёт ───
lines = [
    f'📊 <b>Отчёт парсинга Telegram | {period_str} МСК</b>',
    f'📅 {msk.strftime("%d.%m.%Y")} | {PARSER_NAME}',
    f'🌐 Сервер: GitHub Actions (внешний IP)',
    '',
    '<b>Итого за период:</b>',
    f'📡 Источников проверено: {len(CHANNELS)}',
    f'📰 Новых постов за {period_str}: {total_period}',
    f'✅ Отправлено в публикацию: {total_sent if IS_WORK else total_buf}',
    f'⚪ Без новостей: {total_empty}',
    f'❌ Ошибок доступа: {total_err}',
    '',
    '<b>По каналам:</b>'
]

for s in stats:
    ch = s['ch']
    st = s['status']
    n = s['n']
    if st == 'error':
        lines.append(f'❌ @{ch} — ошибка: {s.get("error","?")}')
    elif st == 'empty':
        lines.append(f'⚪ @{ch} — 0 постов за {period_str}')
    elif st == 'sent':
        t = s['post']['time_msk']
        lines.append(f'✅ @{ch} — найдено {n}, отправлен [{t}] → в публикацию')
    elif st == 'buffered':
        t = s['post']['time_msk']
        lines.append(f'🌙 @{ch} — найдено {n}, [{t}] → ночной буфер')
    elif st == 'n8n_err':
        lines.append(f'⚠️ @{ch} — найдено {n}, ошибка отправки в n8n')

if not IS_WORK:
    lines += ['', f'🌙 Ночной режим: {total_buf} в буфере → публикация в 08:01 МСК']

tg('\n'.join(lines))
print(f"\nДОНЕ: sent={total_sent} buf={total_buf} empty={total_empty} err={total_err}")

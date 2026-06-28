#!/usr/bin/env python3
"""Daily report - отправляет в 20:05 МСК ежедневный отчёт"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

BOT = os.environ.get("BOT_TOKEN", "")
CHAT = "5340000158"
LOG_FILE = "/data/published_log.json"

def tg(m):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": m[:4000], "parse_mode": "HTML"}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10)

msk = datetime.now(timezone.utc) + timedelta(hours=3)
today = msk.strftime("%d.%m.%Y")

logs = []
try:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            logs = json.load(f)
except: pass

# Фильтруем только сегодняшние
today_logs = [l for l in logs if today in l.get("time", "")]

if not today_logs:
    tg(f"📊 <b>Отчёт за {today}</b>

Сегодня публикаций не было.")
else:
    report = [f"📊 <b>Ежедневный отчёт Grandvest за {today}</b>
"]
    report.append(f"Всего публикаций: <b>{len(today_logs)}</b>
")
    
    # По источникам
    sources = {}
    for l in today_logs:
        src = l.get("source_name", "unknown")
        sources[src] = sources.get(src, 0) + 1
    
    report.append("<b>По источникам:</b>")
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        report.append(f"• {src}: {cnt} публикаций")
    
    report.append("
<b>Все публикации:</b>")
    for i, l in enumerate(today_logs, 1):
        line = f"{i}. {l.get('time','?')} | {l.get('source_name','?')}"
        if l.get("source_url"):
            line += f"
   🔗 {l['source_url'][:60]}"
        line += f"
   📝 {l.get('chars',0)} симв | 🖼 {'да' if l.get('has_image') else 'нет'}"
        report.append(line)
    
    tg("
".join(report))
    print(f"Report sent: {len(today_logs)} posts today")

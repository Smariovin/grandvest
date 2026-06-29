#!/usr/bin/env python3
"""Guardian v4 - watches parser health, triggers if needed"""
import json, urllib.request, urllib.parse, os, time, datetime

PAT = os.environ.get('GH_PAT', '')
REPO = 'Smariovin/grandvest'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    d = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        'https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    except: pass

def gh_get(path):
    r = urllib.request.Request('https://api.github.com'+path, headers={
        'Authorization':'token '+PAT, 'Accept':'application/vnd.github.v3+json'})
    with urllib.request.urlopen(r, timeout=15) as resp: return json.loads(resp.read())

def gh_dispatch(workflow):
    r = urllib.request.Request(
        'https://api.github.com/repos/'+REPO+'/actions/workflows/'+workflow+'/dispatches',
        data=json.dumps({'ref':'main'}).encode(),
        headers={'Authorization':'token '+PAT,'Accept':'application/vnd.github.v3+json',
                 'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=15): return True
    except: return False

print('=== Guardian v4 ===')
now = datetime.datetime.now(datetime.timezone.utc)
actions = []

# Проверяем Telegram Parser
runs = gh_get('/repos/'+REPO+'/actions/runs?per_page=20')
tg_runs = [r for r in runs['workflow_runs'] if r['name']=='Telegram Parser' and r['status']=='completed']

if tg_runs:
    last_tg = datetime.datetime.fromisoformat(tg_runs[0]['created_at'].replace('Z','+00:00'))
    age_min = (now - last_tg).total_seconds() / 60
    print(f'Last Telegram Parser: {last_tg.strftime("%H:%M")} UTC ({age_min:.0f} min ago)')
    
    # Если > 90 минут без парсера — запускаем
    if age_min > 90:
        print(f'WARNING: Parser not run for {age_min:.0f} min! Triggering...')
        ok = gh_dispatch('telegram-parser.yml')
        if ok:
            actions.append(f'Парсер Telegram запущен (не запускался {age_min:.0f} мин)')
            print('Telegram Parser triggered!')
        else:
            actions.append('Не удалось запустить Парсер Telegram')
    else:
        print(f'Telegram Parser OK (last {age_min:.0f} min ago)')
else:
    print('No Telegram Parser runs found')

# Проверяем n8n healthz
try:
    urllib.request.urlopen('http://85.239.61.157:5678/healthz', timeout=5)
    print('n8n: UP')
except:
    actions.append('n8n недоступен!')
    tg('<b>ALERT: n8n недоступен!</b>\nПроверь сервер 85.239.61.157')

# Отправляем уведомление только если были действия
if actions:
    tg('<b>Guardian v4</b>\n\n' + '\n'.join('• '+a for a in actions))

print('Done. Actions:', actions)

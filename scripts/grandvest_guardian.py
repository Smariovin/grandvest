#!/usr/bin/env python3
import json, urllib.request, urllib.parse, os, datetime
PAT = os.environ.get('GH_PAT','')
REPO = 'Smariovin/grandvest'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
def gh_dispatch(workflow):
    r = urllib.request.Request(
        'https://api.github.com/repos/'+REPO+'/actions/workflows/'+workflow+'/dispatches',
        data=json.dumps({'ref':'main'}).encode(),
        headers={'Authorization':'token '+PAT,'Accept':'application/vnd.github.v3+json',
                 'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=15): return True
    except: return False
def tg(msg):
    d = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        'https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    except: pass
now = datetime.datetime.now(datetime.timezone.utc)
r = urllib.request.Request('https://api.github.com/repos/'+REPO+'/actions/runs?per_page=20',
    headers={'Authorization':'token '+PAT,'Accept':'application/vnd.github.v3+json'})
with urllib.request.urlopen(r, timeout=15) as resp: runs = json.loads(resp.read())
tg_runs = [r for r in runs['workflow_runs'] if r['name']=='Telegram Parser' and r['status']=='completed']
if tg_runs:
    last = datetime.datetime.fromisoformat(tg_runs[0]['created_at'].replace('Z','+00:00'))
    age = (now - last).total_seconds() / 60
    if age > 90:
        gh_dispatch('telegram-parser.yml')
        tg('Guardian: Парсер Telegram запущен (не запускался '+str(int(age))+' мин)')
try:
    urllib.request.urlopen('http://85.239.61.157:5678/healthz', timeout=5)
except:
    tg('ALERT: n8n недоступен!')
print('Guardian done')

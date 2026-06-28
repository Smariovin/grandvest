#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"

curl -s -c /tmp/n9v2_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/n9v2_ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 << PYEOF
import sys, json, subprocess, os, urllib.request, urllib.parse, re

PAT = os.environ.get('WORKING_PAT','')
BOT = '8672691336:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])

# Новый код узла 9 — передаёт source_url, source_name, parser_name
NODE9 = f"""const postData = \$('8. Подготовка данных поста').first().json;
const postText = postData.tg_post;
const imgData = \$('HTTP Request \u2014 fal.ai').first().json;
const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : '';

// Данные источника
const sourceUrl = postData.source_url || \$input.first().json.source_url || '';
const sourceName = postData.source_name || \$input.first().json.channel || '';
const parserName = 'Парсер Telegram';

if (!postText || postText.length < 10) {{
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}}

console.log('Posting:', postText.length, 'chars, source:', sourceName);

const resp = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{
    'Authorization': 'token {PAT}',
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json'
  }},
  body: JSON.stringify({{
    ref: 'main',
    inputs: {{
      message: postText,
      image_url: imageUrl,
      source_url: sourceUrl,
      source_name: sourceName,
      parser_name: parserName
    }}
  }})
}});

return [{{ json: {{ ok: true, len: postText.length, source: sourceName }} }}];"""

changed = False
for n in nodes:
    name = n.get('name','')
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        n['parameters']['jsCode'] = NODE9
        n['parameters'].pop('code', None)
        changed = True
        print(f"Updated Node9: {name}")

if changed:
    payload = json.dumps(wf, ensure_ascii=False)
    r = subprocess.run(['curl','-s','-b','/tmp/n9v2_ck.txt','-X','PUT',
        'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
        '-H','Content-Type: application/json','-d', payload],
        capture_output=True, text=True, timeout=20)
    result = json.loads(r.stdout)
    saved = len(result.get('data',result).get('nodes',[]))
    print(f"Saved: {saved} nodes")
    tg(f"✅ Узел 9 обновлён: теперь передаёт source_url, source_name, parser_name в publisher")
else:
    tg("⚠️ Node9 не найден")
PYEOF

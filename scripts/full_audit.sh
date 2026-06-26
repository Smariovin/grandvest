#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
DB="/opt/n8n/n8n_data/database.sqlite"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "========================================="
echo "GRANDVEST FULL AUDIT $(date '+%d.%m.%Y %H:%M')"
echo "========================================="

# === 1. n8n STATUS ===
echo -e "\n[1] n8n status"
if curl -s http://localhost:5678/healthz > /dev/null 2>&1; then
    echo "  n8n: RUNNING"
else
    echo "  n8n: DOWN"
    docker start n8n && sleep 15
fi

# === 2. WORKFLOW EXECUTIONS - последние ошибки ===
echo -e "\n[2] Last executions from SQLite"
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()

# Последние 10 executions
try:
    cur.execute('''SELECT id, workflowId, status, startedAt, stoppedAt, data
                   FROM execution_entity 
                   ORDER BY startedAt DESC LIMIT 10''')
    rows = cur.fetchall()
    print(f'  Total recent executions: {len(rows)}')
    for row in rows:
        eid, wid, status, started, stopped, data_raw = row
        try:
            data = json.loads(data_raw) if data_raw else {}
            # Ищем ошибку
            err = ''
            result_data = data.get('resultData', {})
            run_data = result_data.get('runData', {})
            for node_name, node_runs in run_data.items():
                for run in (node_runs or []):
                    if run.get('error'):
                        err = f\" ERR in '{node_name}': {run['error'].get('message','?')[:80]}\"
        except:
            err = ''
        print(f'  [{status}] wf={wid} start={started} {err}')
except Exception as e:
    print(f'  executions table error: {e}')
    # Попробуем другое имя таблицы
    try:
        cur.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
        print('  Tables:', [r[0] for r in cur.fetchall()])
    except: pass

conn.close()
"

# === 3. WORKFLOW NODES - читаем все узлы ===
echo -e "\n[3] All workflow nodes with key params"
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute('SELECT id, name, active, nodes FROM workflow_entity')
for wid, wname, active, nodes_raw in cur.fetchall():
    nodes = json.loads(nodes_raw)
    print(f'\n  WF: {wname!r} ({wid}) active={active}')
    for n in nodes:
        nm = n.get('name','')
        tp = n.get('type','').split('.')[-1]
        params = n.get('parameters',{})
        code = params.get('jsCode', params.get('code',''))
        url = params.get('url','')
        jb = str(params.get('jsonBody','')).strip()
        
        info = f'    [{tp}] {nm!r}'
        if url: info += f' url={url[:60]}'
        if code: info += f' code({len(code)})={code[:80]!r}'
        if jb and jb != '{}':
            # Парсим jsonBody
            clean = jb[1:] if jb.startswith('=') else jb
            try:
                body = json.loads(clean)
                mt = body.get('max_tokens','?')
                model = body.get('model','?')
                info += f' model={model} max_tokens={mt}'
            except:
                info += f' jsonBody(raw)={jb[:60]!r}'
        print(info)
conn.close()
" 2>&1

# === 4. TEST OpenRouter API ===
echo -e "\n[4] Test OpenRouter API"
python3 -c "
import sqlite3, json, urllib.request, urllib.parse

# Читаем OR ключ из БД
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute('SELECT nodes FROM workflow_entity')
or_key = ''
for (nodes_raw,) in cur.fetchall():
    nodes = json.loads(nodes_raw)
    for n in nodes:
        params = n.get('parameters',{})
        headers = params.get('headerParameters',{}).get('parameters',[])
        for h in headers:
            v = str(h.get('value',''))
            if 'sk-or-v1' in v:
                or_key = v.replace('Bearer ','').strip()
conn.close()

if not or_key:
    print('  OR key: NOT FOUND in DB!')
else:
    print(f'  OR key: found ({or_key[:20]}...)')
    # Тест минимального запроса
    try:
        payload = json.dumps({
            'model': 'anthropic/claude-sonnet-4-5',
            'max_tokens': 100,
            'messages': [{'role':'user','content':'Say OK'}]
        }).encode()
        req = urllib.request.Request(
            'https://openrouter.ai/api/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {or_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://grandvest.ru'
            }
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode())
            content = resp.get('choices',[{}])[0].get('message',{}).get('content','')
            usage = resp.get('usage',{})
            print(f'  OR API: OK! Response: {content[:50]!r}')
            print(f'  Usage: {usage}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  OR API ERROR {e.code}: {body[:200]}')
    except Exception as e:
        print(f'  OR API ERROR: {e}')
" 2>&1

# === 5. TEST fal.ai API ===
echo -e "\n[5] Test fal.ai API key"
python3 -c "
import sqlite3, json, urllib.request

conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute('SELECT nodes FROM workflow_entity')
fal_key = ''
for (nodes_raw,) in cur.fetchall():
    nodes = json.loads(nodes_raw)
    for n in nodes:
        params = n.get('parameters',{})
        headers = params.get('headerParameters',{}).get('parameters',[])
        for h in headers:
            v = str(h.get('value',''))
            if 'fal-' in v or 'fal_' in v.lower():
                fal_key = v.replace('Key ','').strip()
        url = params.get('url','')
        if 'fal.run' in url or 'fal.ai' in url:
            # Читаем ключ из Authorization header
            all_params = str(params)
            import re
            keys = re.findall(r'fal-[a-f0-9\-:]+', all_params)
            if keys:
                fal_key = keys[0]
conn.close()

if fal_key:
    print(f'  fal.ai key: found ({fal_key[:20]}...)')
else:
    print('  fal.ai key: checking credentials table...')
    # Проверяем таблицу credentials
    conn2 = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
    cur2 = conn2.cursor()
    try:
        cur2.execute('SELECT name, type, data FROM credentials_entity')
        for cname, ctype, cdata in cur2.fetchall():
            print(f'  Credential: {cname!r} type={ctype}')
    except Exception as e:
        print(f'  credentials error: {e}')
    conn2.close()
" 2>&1

# === 6. TEST Telegram Bot ===
echo -e "\n[6] Test Telegram Bot"
python3 -c "
import urllib.request, json
bot = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
try:
    with urllib.request.urlopen(f'https://api.telegram.org/bot{bot}/getMe', timeout=10) as r:
        d = json.loads(r.read().decode())
        print(f'  Bot: {d[\"result\"][\"username\"]} OK')
except Exception as e:
    print(f'  Bot error: {e}')

# Тест канала
try:
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{bot}/getChat',
        data=b'chat_id=-1003971323034',
        headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode())
        ch = d.get('result',{})
        print(f'  Channel: {ch.get(\"title\",\"?\")} type={ch.get(\"type\",\"?\")}')
        print(f'  Bot is admin: checking...')
except Exception as e:
    print(f'  Channel error: {e}')

# Проверяем права бота в канале
try:
    req2 = urllib.request.Request(
        f'https://api.telegram.org/bot{bot}/getChatMember',
        data=b'chat_id=-1003971323034&user_id=8672691136',
        headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req2, timeout=10) as r:
        d = json.loads(r.read().decode())
        member = d.get('result',{})
        status = member.get('status','?')
        can_post = member.get('can_post_messages', member.get('can_send_messages', '?'))
        print(f'  Bot status in channel: {status}')
        print(f'  Can post: {can_post}')
except Exception as e:
    print(f'  Bot member check error: {e}')
" 2>&1

# === 7. TEST GitHub Actions ===
echo -e "\n[7] GitHub Actions - grandvest-publisher"
GH_PAT="${GH_PAT}"
if [ -n "$GH_PAT" ]; then
    STATUS=$(curl -s -H "Authorization: token $GH_PAT" \
        "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state','?'), d.get('name','?'))")
    echo "  grandvest-publisher: $STATUS"
    
    # Последние runs
    RUNS=$(curl -s -H "Authorization: token $GH_PAT" \
        "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/runs?per_page=5" \
        | python3 -c "
import sys,json
d=json.load(sys.stdin)
for r in d.get('workflow_runs',[])[:5]:
    t=r.get('created_at','?')[11:16]
    print(f\"  Run #{r['run_number']} {r['conclusion']} {t} UTC\")
")
    echo "$RUNS"
else
    echo "  GH_PAT not set"
fi

# === 8. ЖИВОЙ ТЕСТ ПОЛНОГО ЦИКЛА ===
echo -e "\n[8] Live end-to-end test"

# Отправляем напрямую в n8n webhook
RESP=$(curl -s -X POST http://localhost:5678/webhook/telegram-parser \
    -H 'Content-Type: application/json' \
    -d '{
        "channel": "test_audit",
        "html": "<div class=\"tgme_widget_message_text js-message_text\">Офисный рынок Москвы 2026: вакантность класса А достигла минимума за 5 лет и составила 7.8% по данным CBRE. В ЦАО ставки аренды выросли до 48000 руб за кв м в год, в Москва-Сити до 65000 руб. Спрос со стороны IT-компаний вырос на 34% год к году.</div><time datetime=\"2026-06-26T09:30:00+00:00\">09:30</time>"
    }' 2>&1)

echo "  Webhook response: $RESP"

# Ждём 30 сек и смотрим что произошло в executions
sleep 30
echo -e "\n  Executions after webhook:"
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
try:
    cur.execute('''SELECT id, workflowId, status, startedAt, data 
                   FROM execution_entity 
                   ORDER BY startedAt DESC LIMIT 3''')
    for eid, wid, status, started, data_raw in cur.fetchall():
        try:
            data = json.loads(data_raw) if data_raw else {}
            result = data.get('resultData',{})
            run_data = result.get('runData',{})
            nodes_run = list(run_data.keys())
            last_node = nodes_run[-1] if nodes_run else '?'
            err = result.get('error',{})
            err_msg = err.get('message','') if err else ''
        except:
            last_node = '?'
            err_msg = ''
        print(f'  [{status}] wf={wid} t={started} last_node={last_node!r} {err_msg[:60]}')
except Exception as e:
    print(f'  Error: {e}')
conn.close()
" 2>&1

# === 9. ИТОГОВЫЙ ОТЧЁТ ===
echo -e "\n========================================="
echo "AUDIT COMPLETE"
echo "========================================="


import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, http.cookiejar
DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = '5340000158'
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'

def tg(msg):
    if not BOT: print(msg); return
    d = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request('https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    except Exception as e: print('TG err:',e)

# URL замены для нерабочих источников
REPLACEMENTS = {
    'vedomosti': 'https://news.google.com/rss/search?q=%D1%82%D0%BE%D1%80%D0%B3%D0%BE%D0%B2%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru',
    'kommersant': 'https://news.google.com/rss/search?q=%D0%B4%D0%B5%D0%B2%D0%B5%D0%BB%D0%BE%D0%BF%D0%BC%D0%B5%D0%BD%D1%82+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru',
    'cian.ru/rss': 'https://news.google.com/rss/search?q=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0-%D0%A1%D0%B8%D1%82%D0%B8+%D0%BE%D1%84%D0%B8%D1%81%D1%8B&hl=ru&gl=RU&ceid=RU:ru',
    'realty.rbc': 'https://news.google.com/rss/search?q=%D0%B8%D0%BD%D0%B2%D0%B5%D1%81%D1%82%D0%B8%D1%86%D0%B8%D0%B8+%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru',
}

print('=== SIMPLE URL FIX ===')
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('SELECT id, name, nodes FROM workflow_entity WHERE id=?', (RSS_WF_ID,))
row = cur.fetchone()
if not row: print('NOT FOUND'); exit(1)
wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []

for n in nodes:
    ntype = n.get('type','')
    params = n.get('parameters',{})
    name = n.get('name','')
    url = params.get('url','')
    if ntype != 'n8n-nodes-base.httpRequest': continue
    for bad_key, good_url in REPLACEMENTS.items():
        if bad_key in url:
            print('Replacing ' + name + ': ' + url[:50])
            params['url'] = good_url
            params['method'] = 'GET'
            params.pop('bodyContentType', None)
            params.pop('jsonBody', None)
            n['parameters'] = params
            fixes.append(name + ' -> Google News')
            break

# Сброс StaticData
try:
    cur.execute('UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type=?',
               (json.dumps({'publishedTitles':[]}), RSS_WF_ID, 'global'))
    print('StaticData reset')
except Exception as e:
    print('StaticData err: ' + str(e))

cur.execute('UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?',
           (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()
print('Fixes: ' + str(fixes))

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try: urllib.request.urlopen('http://localhost:5678/healthz',timeout=5); print('n8n UP!'); break
    except: pass

time.sleep(3)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({'emailOrLdapLoginId':'admin@grandvest.ru','password':'Grandvest2026!'}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request('http://localhost:5678/rest/login',
        data=ld, headers={'Content-Type':'application/json'}, method='POST'), timeout=10)
    run_req = urllib.request.Request(
        'http://localhost:5678/rest/workflows/' + RSS_WF_ID + '/run',
        data=json.dumps({'runData':{},'startNodes':[],'destinationNode':''}).encode(),
        headers={'Content-Type':'application/json'}, method='POST')
    with opener.open(run_req, timeout=30) as r:
        resp = json.loads(r.read())
    exec_id = resp.get('data',{}).get('executionId') or resp.get('executionId','?')
    print('Started: ' + str(exec_id))
except Exception as e:
    print('Run err: ' + str(e)[:80])

tg('<b>RSS SOURCES FIXED</b>

Замены:
' + '
'.join(fixes) +
   '

StaticData: сброшена
Запущен: exec_id=' + str(exec_id) +
   '
Жди 90 сек — пост в @grandvest_realty!')
print('DONE')

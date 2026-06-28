import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os
DB = '/opt/n8n/n8n_data/database.sqlite'
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'
BOT = os.environ.get('TG_BOT','')
CHAT = '5340000158'

DEDUP = 'const items = $input.all();\n'
DEDUP += 'const sd = $getWorkflowStaticData("global");\n'
DEDUP += 'if (!sd.publishedTitles) sd.publishedTitles = [];\n'
DEDUP += 'const unique = [];\n'
DEDUP += 'for (const item of items) {\n'
DEDUP += '  const t = (item.json.title || item.json.text || "").trim().toLowerCase().substring(0,80);\n'
DEDUP += '  if (!t) continue;\n'
DEDUP += '  if (!sd.publishedTitles.some(p => p.substring(0,80) === t)) unique.push(item);\n'
DEDUP += '  else console.log("Dup:", t.substring(0,40));\n'
DEDUP += '}\n'
DEDUP += 'if (sd.publishedTitles.length > 500) sd.publishedTitles = sd.publishedTitles.slice(-300);\n'
DEDUP += 'console.log("Dedup: in=" + items.length + " out=" + unique.length);\n'
DEDUP += 'return unique.slice(0,1);'

WRITE = 'const item = $input.first().json;\n'
WRITE += 'const t = (item.title||item.text||item.tg_post||"").trim().toLowerCase().substring(0,80);\n'
WRITE += 'if (t) {\n'
WRITE += '  const sd = $getWorkflowStaticData("global");\n'
WRITE += '  if (!sd.publishedTitles) sd.publishedTitles = [];\n'
WRITE += '  if (!sd.publishedTitles.includes(t)) sd.publishedTitles.push(t);\n'
WRITE += '}\n'
WRITE += 'return [$input.first()];'

print('=== FIX FS NODES ===')
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('SELECT id,name,nodes FROM workflow_entity WHERE id=?', (RSS_WF_ID,))
row = cur.fetchone()
if not row: print('NOT FOUND'); exit(1)
wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    if ntype != 'n8n-nodes-base.code': continue
    code = params.get('jsCode','')
    print('Code [' + name + ']: has_fs=' + str('require(' in code and 'fs' in code))
    if 'require(' in code and 'fs' in code:
        print('  FIXING: ' + name)
        params['jsCode'] = WRITE if 'writeFileSync' in code else DEDUP
        n['parameters'] = params
        fixes.append(name)
if not fixes:
    print('No require(fs) found - force by name')
    for n in nodes:
        name = n.get('name','')
        if n.get('type') != 'n8n-nodes-base.code': continue
        if 'JavaScript3' in name:
            n['parameters']['jsCode'] = DEDUP
            fixes.append('FORCED:' + name)
        elif 'JavaScript4' in name:
            n['parameters']['jsCode'] = WRITE
            fixes.append('FORCED:' + name)
cur.execute('UPDATE workflow_entity SET nodes=?,active=1 WHERE id=?',
    (json.dumps(nodes,ensure_ascii=False), wf_id))
conn.commit()
conn.close()
print('Fixes: ' + str(fixes))
subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try: urllib.request.urlopen('http://localhost:5678/healthz',timeout=5); print('UP!'); break
    except: pass
os.makedirs('/data',exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([],f)
def tg(msg):
    if not BOT: return
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request('https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=10)
    except: pass
tg('<b>RSS CODE FIX</b>\nИсправлено: '+str(fixes)+'\nТеперь нажми Execute workflow в n8n UI')
print('DONE')

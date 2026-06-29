import urllib.request, urllib.parse, json, os, http.cookiejar
TG_BOT = os.environ.get('TG_BOT','')
GH_PAT = os.environ.get('GH_PAT','')
CHAT = '5340000158'
N8N = 'http://85.239.61.157:5678'
TG_WF = 'F24jvKiXJIs4wRiZ'

def tg(msg):
    d = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    urllib.request.urlopen(urllib.request.Request(
        'https://api.telegram.org/bot'+TG_BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    print('TG sent')

# Login
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({'emailOrLdapLoginId':'admin@grandvest.ru','password':'Grandvest2026!'}).encode()
opener.open(urllib.request.Request(N8N+'/rest/login',
    data=ld, headers={'Content-Type':'application/json'}, method='POST'), timeout=15)
print('n8n login OK')

# Get workflow nodes
with opener.open(N8N+'/rest/workflows/'+TG_WF, timeout=15) as r:
    wf_data = json.loads(r.read())
nodes = wf_data.get('data', wf_data).get('nodes', [])
print(f'Nodes: {len(nodes)}')

node9_code = ''
for n in nodes:
    name = n.get('name','')
    params = n.get('parameters',{})
    if '9.' in name or ('Отправка' in name and 'Telegram' in name):
        node9_code = params.get('jsCode','')
        print('Node9:', name, '| code len:', len(node9_code))
        print(node9_code[:500])

# Get last execution
with opener.open(N8N+'/rest/executions?limit=1&workflowId='+TG_WF, timeout=15) as r:
    ed = json.loads(r.read())
execs = ed.get('data',{}).get('data', ed.get('data',[]))

trace = []
if execs:
    ex = execs[0]
    status = ex.get('status','?')
    started = str(ex.get('startedAt','?'))[:16]
    rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
    order = ['Webhook','2. Дедупликация входящих','1. Парсинг HTML Telegram',
             'Claude — оценка поста','Code — фильтр оценки',
             '6. Извлечение текста поста','HTTP Request — генерация поста',
             '8. Подготовка данных поста','HTTP Request — fal.ai',
             '9. Отправка в Telegram','10. Запись в дедупликацию']
    trace.append(status+' @ '+started)
    for nn in order:
        nd = rd.get(nn)
        if nd is None:
            trace.append('  -не запускался')
            continue
        if nd and nd[0]:
            items = nd[0].get('data',{}).get('main',[[]])[0]
            has = bool(items and items[0])
            err = nd[0].get('error')
            if err:
                trace.append('ERR '+nn[:25]+': '+str(err)[:60])
            elif has:
                s2 = items[0].get('json',{})
                keys = list(s2.keys())[:5]
                trace.append('OK  '+nn[:25]+': '+str(keys))
            else:
                trace.append('STOP '+nn[:25]+': NO OUTPUT')

msg = '<b>TRACE 13:20 MSK</b>\n\n'
msg += '\n'.join(trace) + '\n\n'
msg += '<b>Узел 9 (первые 400):</b>\n' + node9_code[:400]
tg(msg)
print('DONE')

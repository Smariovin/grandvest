import sqlite3,json,urllib.request,urllib.parse,os,time
DB='/opt/n8n/n8n_data/database.sqlite'
try: BOT=open('/tmp/.tb').read().strip()
except: BOT=''
CHAT='5340000158'
def tg(m):
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request('https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    except Exception as e: print('TG:',e)
conn=sqlite3.connect(DB)
cur=conn.cursor()
msgs=[]
for wf_id,label in [('F24jvKiXJIs4wRiZ','TG'),('SIPnV2mqmgMqUkLb','RSS')]:
    cur.execute('SELECT nodes FROM workflow_entity WHERE id=?',(wf_id,))
    row=cur.fetchone()
    if not row: continue
    nodes=json.loads(row[0])
    for n in nodes:
        nm=n.get('name','');nt=n.get('type','');p=n.get('parameters',{})
        if nt=='n8n-nodes-base.code':
            msgs.append('['+label+'] CODE '+nm+'\n'+p.get('jsCode','')[:200])
        if nt=='n8n-nodes-base.httpRequest' and 'openrouter' in p.get('url','').lower():
            msgs.append('['+label+'] OR '+nm+'\nbct='+p.get('bodyContentType','?')+'\n'+str(p.get('jsonBody',''))[:250])
conn.close()
for i in range(0,len(msgs),3):
    tg('<b>NODES</b>\n\n'+'\n---\n'.join(msgs[i:i+3]))
    time.sleep(1)
print('OK',len(msgs))

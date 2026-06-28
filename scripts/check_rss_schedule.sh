#!/bin/bash
curl -s -c /tmp/sched_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/sched_ck.txt 'http://localhost:5678/rest/workflows' | python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691336:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

d=json.load(sys.stdin)
for wf in d.get('data',[]):
    name=wf.get('name','')
    wid=wf.get('id','')
    print(f'WF: {name} ({wid})')
    # Ищем Schedule Trigger
    for n in wf.get('nodes',[]):
        if 'scheduleTrigger' in n.get('type','') or 'schedule' in n.get('type','').lower():
            params=n.get('parameters',{})
            print(f'  Schedule: {params}')
" 2>&1

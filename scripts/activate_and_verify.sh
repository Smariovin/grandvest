#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

# Логин
curl -s -c /tmp/av_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Читаем текущий код узла 9 через API
echo "=== Current Node9 via API ==="
curl -s -b /tmp/av_ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys,json,re,os,urllib.request,urllib.parse,subprocess

PAT=os.environ.get('WORKING_PAT','')
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
wf=d.get('data',d)
nodes=wf.get('nodes',[])

report=['<b>Node9 via API (текущий):</b>']
changed=False

for n in nodes:
    name=n.get('name','')
    params=n.get('parameters',{})
    code=params.get('jsCode',params.get('code',''))
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        has_wrong_url='telegram-publisher' in code
        has_bearer='Bearer' in code
        has_stringify='JSON.stringify' in code
        has_correct_url='grandvest-publisher' in code
        tokens=re.findall(r'ghp_[A-Za-z0-9]{10,}',code)
        
        report.append(f'Name: {name}')
        report.append(f'wrong_url: {has_wrong_url}')
        report.append(f'has_Bearer: {has_bearer}')
        report.append(f'has_stringify: {has_stringify}')
        report.append(f'correct_url: {has_correct_url}')
        report.append(f'tokens: {[t[:15] for t in tokens]}')
        report.append(f'code[:150]: {code[:150]!r}')
        
        # Если всё ещё неправильный URL — патчим прямо сейчас через API
        if has_wrong_url or has_bearer or not has_stringify:
            report.append('NEEDS FIX - patching now...')
            
            CORRECT = (
                'const postText = \$(\"8. Подготовка данных поста\").first().json.tg_post;\\n'
                'const imgData = \$(\"HTTP Request — fal.ai\").first().json;\\n'
                'const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : \"\";\\n'
                '\\n'
                'if (!postText || postText.length < 10) {\\n'
                '  throw new Error(\"tg_post пустой: \" + JSON.stringify(postText));\\n'
                '}\\n'
                '\\n'
                'const resp = await this.helpers.httpRequest({\\n'
                '  method: \"POST\",\\n'
                '  url: \"https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches\",\\n'
                '  headers: {\\n'
                '    \"Authorization\": \"token ' + PAT + '\",\\n'
                '    \"Accept\": \"application/vnd.github+json\",\\n'
                '    \"Content-Type\": \"application/json\"\\n'
                '  },\\n'
                '  body: JSON.stringify({\\n'
                '    ref: \"main\",\\n'
                '    inputs: {\\n'
                '      message: postText,\\n'
                '      image_url: imageUrl\\n'
                '    }\\n'
                '  })\\n'
                '});\\n'
                '\\n'
                'return [{ json: { ok: true, len: postText.length } }];'
            )
            
            n['parameters']['jsCode'] = CORRECT
            n['parameters'].pop('code',None)
            changed=True
            report.append(f'Patched with correct code!')

if changed:
    # Сохраняем
    payload=json.dumps(wf,ensure_ascii=False)
    r=subprocess.run(['curl','-s','-b','/tmp/av_ck.txt','-X','PUT',
        'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
        '-H','Content-Type: application/json','-d',payload],
        capture_output=True,text=True,timeout=20)
    result=json.loads(r.stdout)
    saved=len(result.get('data',result).get('nodes',[]))
    report.append(f'Saved via API! {saved} nodes')
    
    # Деактивируем и активируем заново чтобы n8n перезагрузил
    subprocess.run(['curl','-s','-b','/tmp/av_ck.txt','-X','POST',
        'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/deactivate',
        '-H','Content-Type: application/json','-d','{}'],
        capture_output=True,timeout=10)
    import time; time.sleep(2)
    subprocess.run(['curl','-s','-b','/tmp/av_ck.txt','-X','POST',
        'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/activate',
        '-H','Content-Type: application/json','-d','{}'],
        capture_output=True,timeout=10)
    report.append('Deactivated + Activated!')

tg('\n'.join(report))
print('\n'.join(report))
" 2>&1

# Сбрасываем деdup и тестируем
echo '[]' > /data/published_titles.json
sleep 3

curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Инвестиции в складскую недвижимость Москвы и Московской области выросли на 40 процентов в первом полугодии 2026 года и составили 120 миллиардов рублей. Вакантность рынка достигла исторического минимума 0.3 процента. Ставки аренды складов класса А выросли до 14000 рублей за кв м в год по данным CORE.XP.</div><time datetime=\"2026-06-27T11:45:00+00:00\">11:45</time>"}' \
  && echo "Webhook sent!"

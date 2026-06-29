#!/usr/bin/env python3
"""
RESTORE RSS ORIGINAL
Восстанавливаем оригинальный RSS workflow:
- 9 источников: Google News x6 + Ведомости + РИА + Циан
- Оригинальный Code парсер с this.helpers.httpRequest  
- Правильная дедупликация через StaticData
"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, http.cookiejar

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT', '')
CHAT = '5340000158'
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'

def tg(msg):
    if not BOT:
        print(msg)
        return
    d = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4096], 'parse_mode': 'HTML'}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request('https://api.telegram.org/bot' + BOT + '/sendMessage', data=d, method='POST'),
            timeout=15
        )
    except Exception as e:
        print('TG err:', e)

print('=== RESTORE RSS ORIGINAL ===')

subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('SELECT id, name, nodes FROM workflow_entity WHERE id=?', (RSS_WF_ID,))
row = cur.fetchone()
if not row:
    print('NOT FOUND'); exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []

print('Current nodes: ' + str(len(nodes)))
for n in nodes:
    print('  ' + n.get('name','') + ' | ' + n.get('type','').split('.')[-1])

# 1. Восстанавливаем URL источников (возвращаем оригинальные)
ORIGINAL_URLS = {
    'HTTP Request': 'https://news.google.com/rss/search?q=%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request1': 'https://news.google.com/rss/search?q=%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%BE%D1%84%D0%B8%D1%81%D0%BE%D0%B2+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request2': 'https://news.google.com/rss/search?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request3': 'https://news.google.com/rss/search?q=%D1%82%D0%BE%D1%80%D0%B3%D0%BE%D0%B2%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request4': 'https://news.google.com/rss/search?q=%D0%B4%D0%B5%D0%B2%D0%B5%D0%BB%D0%BE%D0%BF%D0%BC%D0%B5%D0%BD%D1%82+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request5': 'https://news.google.com/rss/search?q=%D0%B8%D0%BD%D0%B2%D0%B5%D1%81%D1%82%D0%B8%D1%86%D0%B8%D0%B8+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru',
    'HTTP Request10': 'https://www.vedomosti.ru/rss/rubric/realty',
    'РИА Недвижимость': 'https://realty.ria.ru/export/rss2/index.xml',
    'Циан': 'https://www.cian.ru/rss/',
}

# 2. Оригинальный код парсера XML (Code in JavaScript)
PARSER_CODE = """// Парсинг RSS XML из всех источников
const items = [];
const allInputs = $input.all();
const sourceItems = $('Code in JavaScript').first().json; // fallback

for (const input of allInputs) {
  try {
    const xmlStr = input.json.data || input.json.body || '';
    if (!xmlStr || typeof xmlStr !== 'string') continue;
    
    // Парсим XML
    const itemMatches = xmlStr.match(/<item[^>]*>([\s\S]*?)<\/item>/g) || [];
    
    for (const itemXml of itemMatches) {
      // Извлекаем поля
      const titleMatch = itemXml.match(/<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>/s);
      const linkMatch = itemXml.match(/<link>(.*?)<\/link>/s) || itemXml.match(/<guid[^>]*>(.*?)<\/guid>/s);
      const descMatch = itemXml.match(/<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/description>/s);
      const pubMatch = itemXml.match(/<pubDate>(.*?)<\/pubDate>/s);
      const sourceMatch = itemXml.match(/<source[^>]*>(.*?)<\/source>/s);
      
      const title = (titleMatch ? titleMatch[1] : '').trim().replace(/<[^>]+>/g, '');
      const link = (linkMatch ? linkMatch[1] : '').trim();
      const description = (descMatch ? descMatch[1] : '').trim().replace(/<[^>]+>/g, '').substring(0, 500);
      const pubDate = pubMatch ? pubMatch[1].trim() : '';
      const source = sourceMatch ? sourceMatch[1].trim() : '';
      
      if (!title || title.length < 5) continue;
      
      // Фильтр по ключевым словам недвижимости
      const text = (title + ' ' + description).toLowerCase();
      const keywords = ['недвижимост', 'аренд', 'офис', 'склад', 'торгов', 'девелопм', 'инвестиц', 'ставк', 'вакантност', 'м2', 'кв.м', 'бизнес-центр', 'бц ', ' тц ', 'логистик'];
      const hasKeyword = keywords.some(k => text.includes(k));
      
      if (!hasKeyword) continue;
      
      // Фильтр по дате - только за последние 48 часов
      if (pubDate) {
        const pub = new Date(pubDate);
        const now = new Date();
        const diffHours = (now - pub) / (1000 * 60 * 60);
        if (diffHours > 48) continue;
      }
      
      items.push({
        json: {
          title: title,
          link: link,
          description: description,
          source: source || link,
          pub_date: pubDate,
          text: title + '. ' + description
        }
      });
    }
  } catch(e) {
    console.log('Parse error:', e.message);
  }
}

console.log('Parsed RSS items:', items.length);
return items.slice(0, 20);"""

# 3. Оригинальный код дедупликации (Code in JavaScript3)
DEDUP_CODE = """const items = $input.all();
const sd = $getWorkflowStaticData('global');
if (!sd.publishedTitles) sd.publishedTitles = [];
const unique = [];
for (const item of items) {
  const t = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 80);
  if (!t) continue;
  if (!sd.publishedTitles.some(p => p.substring(0, 80) === t)) {
    unique.push(item);
  } else {
    console.log('Dup skipped:', t.substring(0, 40));
  }
}
if (sd.publishedTitles.length > 500) sd.publishedTitles = sd.publishedTitles.slice(-300);
console.log('Dedup: in=' + items.length + ' out=' + unique.length);
return unique.slice(0, 1);"""

# 4. Запись в дедупликацию (Code in JavaScript4)  
WRITE_CODE = """const item = $input.first().json;
const t = (item.title || item.text || item.tg_post || '').trim().toLowerCase().substring(0, 80);
if (t) {
  const sd = $getWorkflowStaticData('global');
  if (!sd.publishedTitles) sd.publishedTitles = [];
  if (!sd.publishedTitles.includes(t)) sd.publishedTitles.push(t);
}
return [$input.first()];"""

# Применяем исправления к узлам
for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})

    # Восстанавливаем URL источников
    if ntype == 'n8n-nodes-base.httpRequest' and name in ORIGINAL_URLS:
        old_url = params.get('url', '')
        new_url = ORIGINAL_URLS[name]
        if old_url != new_url:
            params['url'] = new_url
            params['method'] = 'GET'
            params.pop('bodyContentType', None)
            params.pop('jsonBody', None)
            params.pop('specifyBody', None)
            n['parameters'] = params
            fixes.append('URL restored: ' + name)
            print('URL fixed: ' + name)

    # Восстанавливаем парсер XML
    elif ntype == 'n8n-nodes-base.code' and name == 'Code in JavaScript':
        params['jsCode'] = PARSER_CODE
        n['parameters'] = params
        fixes.append('Parser code restored')
        print('Parser restored')

    # Восстанавливаем дедупликацию
    elif ntype == 'n8n-nodes-base.code' and name == 'Code in JavaScript3':
        params['jsCode'] = DEDUP_CODE
        n['parameters'] = params
        fixes.append('Dedup code restored: Code in JavaScript3')
        print('Dedup3 restored')

    # Восстанавливаем запись дедупликации
    elif ntype == 'n8n-nodes-base.code' and name == 'Code in JavaScript4':
        params['jsCode'] = WRITE_CODE
        n['parameters'] = params
        fixes.append('Write dedup restored: Code in JavaScript4')
        print('Write4 restored')

    # Убеждаемся что OpenRouter scoring node имеет bct=json
    elif ntype == 'n8n-nodes-base.httpRequest' and name == 'HTTP Request6':
        if params.get('bodyContentType') != 'json':
            params['bodyContentType'] = 'json'
            params['specifyBody'] = 'json'
            n['parameters'] = params
            fixes.append('HTTP Request6: bct=json')

# Сброс StaticData
try:
    cur.execute(
        'UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type=?',
        (json.dumps({'publishedTitles': []}), RSS_WF_ID, 'global')
    )
    fixes.append('StaticData reset')
    print('StaticData reset')
except Exception as e:
    print('StaticData err: ' + str(e))

cur.execute(
    'UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?',
    (json.dumps(nodes, ensure_ascii=False), wf_id)
)
conn.commit()
conn.close()
print('Saved fixes: ' + str(fixes))

# Рестарт n8n
subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print('n8n UP!')
        break
    except:
        pass

time.sleep(3)

# Запуск RSS
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({'emailOrLdapLoginId': 'admin@grandvest.ru', 'password': 'Grandvest2026!'}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request('http://localhost:5678/rest/login',
        data=ld, headers={'Content-Type': 'application/json'}, method='POST'), timeout=10)
    run_req = urllib.request.Request(
        'http://localhost:5678/rest/workflows/' + RSS_WF_ID + '/run',
        data=json.dumps({'runData': {}, 'startNodes': [], 'destinationNode': ''}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with opener.open(run_req, timeout=30) as r:
        resp = json.loads(r.read())
    exec_id = resp.get('data', {}).get('executionId') or resp.get('executionId', '?')
    print('RSS started: ' + str(exec_id))
except Exception as e:
    print('Run err: ' + str(e)[:100])

lines = ['<b>RSS RESTORED</b>', '']
lines.append('<b>Исправлено:</b>')
lines += ['• ' + f for f in fixes]
lines += ['', '<b>Источники:</b>',
    '• Google News x6 (ком.недвижимость, аренда офисов, склады, торговая, девелопмент, инвестиции)',
    '• Ведомости RSS', '• РИА Недвижимость', '• Циан',
    '', 'StaticData: сброшена',
    'Запущен: exec_id=' + str(exec_id),
    'Жди 90 сек — пост в @grandvest_realty!']
tg('\n'.join(lines))
print('DONE')

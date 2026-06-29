import urllib.request, urllib.parse, os, re
BOT = os.environ.get('TG_BOT','')
CHAT = '5340000158'

def tg(msg):
    if not BOT: print(msg); return
    d = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request('https://api.telegram.org/bot'+BOT+'/sendMessage',data=d,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

sources = [
    ('Google: ком.недвижимость', 'https://news.google.com/rss/search?q=%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru'),
    ('Google: аренда офисов', 'https://news.google.com/rss/search?q=%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%BE%D1%84%D0%B8%D1%81%D0%BE%D0%B2+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru'),
    ('Google: склады', 'https://news.google.com/rss/search?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0&hl=ru&gl=RU&ceid=RU:ru'),
    ('РИА Недвижимость', 'https://realty.ria.ru/export/rss2/index.xml'),
    ('Ведомости', 'https://www.vedomosti.ru/rss/rubric/realty'),
    ('Коммерсант', 'https://www.kommersant.ru/RSS/section-realty.xml'),
    ('RBC Realty', 'https://realty.rbc.ru/v1/export/rss/news'),
    ('Циан', 'https://www.cian.ru/rss/'),
    ('RSSHub local', 'http://localhost:1200/'),
]

results = []
for name, url in sources:
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; RSS)'})
        resp = urllib.request.urlopen(req, timeout=8)
        content = resp.read()
        items = len(re.findall(b'<item>', content))
        icon = 'OK' if items > 0 else 'EMPTY'
        results.append(icon + ' ' + str(items) + 'i  ' + name)
    except urllib.error.HTTPError as e:
        results.append('HTTP' + str(e.code) + '   ' + name)
    except Exception as e:
        results.append('ERR    ' + name + ': ' + str(e)[:25])

tg('<b>RSS тест с VPS</b>

' + '
'.join(results))
print('Done:', results)

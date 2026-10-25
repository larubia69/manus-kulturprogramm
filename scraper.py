#!/usr/bin/env python3
"""Manus Kulturprogramm: publicly accessible event listings, conservative parsing."""
import json,re,hashlib,datetime as dt,time,html
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).parent
DEFAULT_SOURCES=[('Villa Rot','https://villa-rot.de/'),('Stellwerk Schelklingen','https://www.stellwerk-schelklingen.com/'),('Bonanzbar','https://bonanzbar.jimdofree.com/'),('ROXY Ulm','https://www.roxy.ulm.de/programm/programm.php'),('Club Manufaktur','https://www.club-manufaktur.de/kategorie/alle-events/'),('Birkenried','https://www.birkenried.de/termine/'),('Aegis Literatur','https://aegis-literatur.buchhandlung.de/shop/magazine/152252/veranstaltungen.html'),('Livegigs Ulm','https://www.livegigs.de/venues/ulm'),('Pauluskirche','https://www.pauluskirche-ulm.de/kirchen-musik.html'),('DONAU 3 FM','https://www.donau3fm.de/regionale-events/'),('Rausgegangen Ulm','https://rausgegangen.de/ulm/'),('Was geht?','https://www.wasgehtapp.de/index.php?radius=20&select_ort=1&ort=Ulm&x=9.98489&y=48.3917&region=01'),('GOLD','https://dasgold.org/programm/')]
def load_sources():
 data=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
 return [(x['name'].strip(), x['url'].strip()) for x in data if x.get('enabled',True) and x.get('name') and x.get('url','').startswith(('https://','http://'))]
MONTHS={'jan':1,'feb':2,'mär':3,'mae':3,'mar':3,'apr':4,'mai':5,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'okt':10,'oct':10,'nov':11,'dez':12,'dec':12}
SKIP=re.compile(r'kino|kinofilm|filmvorführung|familienkonzert|kinder|familienprogramm|kids\b|jugendtheater|geschlossene gesellschaft|privatveranstaltung',re.I)
def clean_text(value):
 """Decode nested HTML entities and remove HTML tags from event text."""
 text=str(value or '')
 for _ in range(4):
  decoded=html.unescape(text)
  if decoded==text:break
  text=decoded
 text=BeautifulSoup(text,'html.parser').get_text(' ',strip=True)
 return ' '.join(text.replace('\xa0',' ').split())

def short_description(value,limit=220):
 text=clean_text(value)
 if len(text)<=limit:return text
 fragment=text[:limit+1]
 # Prefer ending at a sentence boundary; otherwise at a word boundary.
 breaks=list(re.finditer(r'[.!?](?=\s|$)',fragment))
 if breaks and breaks[-1].end()>=limit//2:
  return fragment[:breaks[-1].end()].strip()
 return fragment[:limit].rsplit(' ',1)[0].rstrip(' ,;:–-')+' …'

def category(text,details=''):
 """Classify using title first, not potentially unrelated description keywords."""
 title=clean_text(text).lower()
 extra=clean_text(details).lower()
 rules=[
  ('Club',r'party|\bdj\b|disco|clubnacht|dancefloor|tanz|dance|rave|90.s|nachtleben'),
  ('Kunst',r'ausstellung|galerie|vernissage|\bkunst\b|exhibition'),
  ('Bühne',r'comedy|kabarett|theater|bühne|poetry\s*slam|schauspiel|impro'),
  ('Literatur',r'lesung|buch|literatur|workshop|vortrag|diskussion|\btalk\b|stammtisch|gespräch|podium')]
 for name,pattern in rules:
  if re.search(pattern,title,re.I):return name
 # Only use explicitly marked event types in descriptions, not incidental mentions.
 for name,pattern in rules:
  if re.search(r'(?:kategorie|genre|veranstaltungsart|format)\s*[:\-]\s*(?:'+pattern+r')\b',extra,re.I):return name
 return 'Konzerte'
def valid(date,title):
 try: day=dt.date.fromisoformat(date)
 except (ValueError,TypeError):return False
 return day >= dt.date.today()-dt.timedelta(days=1) and day <= dt.date.today()+dt.timedelta(days=420) and bool(title.strip()) and not SKIP.search(title)
def record(date,title,place,url,time='',details='',genre=None,end=None):
 title=clean_text(title)
 details=clean_text(details)
 if not valid(date,title):return None
 key=(date+'|'+title.lower()+'|'+place.lower()).encode()
 return dict(id=hashlib.sha256(key).hexdigest()[:16],date=date,title=title,place=place,genre=genre or category(title,details),time=time,url=url,details=short_description(details),end=end)
def fetch(url):
 r=requests.get(url,headers={'User-Agent':'Manus Kulturprogramm/1.0 (personal noncommercial events indexer)'},timeout=9)
 r.raise_for_status();return BeautifulSoup(r.text,'html.parser')
def flatten_jsonld(obj):
 if isinstance(obj,list):
  for x in obj:yield from flatten_jsonld(x)
 elif isinstance(obj,dict):
  if obj.get('@type')=='Event' or 'Event' in (obj.get('@type') or []): yield obj
  for key in ('@graph','itemListElement','mainEntity'):
   if key in obj:yield from flatten_jsonld(obj[key])
def ld_events(soup,name,base):
 found=[]
 for tag in soup.select('script[type="application/ld+json"]'):
  try:data=json.loads(tag.string or tag.get_text())
  except (ValueError,TypeError):continue
  for item in flatten_jsonld(data):
   start=str(item.get('startDate') or '')
   match=re.match(r'(\d{4}-\d\d-\d\d)(?:T(\d\d:\d\d))?',start)
   if not match:continue
   title=str(item.get('name') or '')
   desc=clean_text(item.get('description') or '')
   if SKIP.search(title+' '+desc[:100]):continue
   ev=record(match[1],title,name,str(item.get('url') or base),match[2] or '',desc)
   if ev:found.append(ev)
 return found
def parse_gold(soup,base):
 out=[]
 # Upcoming programme entries are links after dates, plus optional time and type.
 for txt in soup.find_all(string=re.compile(r'\b\d{2}\.\d{2}\.20\d{2}\b')):
  m=re.search(r'(\d{2})\.(\d{2})\.(20\d{2})\s*\|\s*(\d{1,2})?\s*h?',str(txt))
  if not m:continue
  parent=txt.parent
  link=parent.find_next('a',href=True)
  if not link:continue
  title=link.get_text(' ',strip=True)
  if not title or title.lower()=='more…':continue
  date=f'{m[3]}-{m[2]}-{m[1]}'
  ev=record(date,title,'GOLD',urljoin(base,link['href']),f'{int(m[4]):02d}:00' if m[4] else '',str(txt),category(title,str(txt)))
  if ev:out.append(ev)
 return out
def parse_bonanz(soup,base):
 out=[]; text=soup.get_text('\n',strip=True); year=dt.date.today().year
 # concise date + title lines, including NEXT SHOW section
 for line in text.splitlines():
  m=re.search(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.\s*(?:-|\s)*(.{3,95})',line)
  if not m:continue
  day,month=int(m[1]),int(m[2]);title=m[3].split(' - TICKET')[0].strip(' -')
  if not title or re.search(r'geschlossen|private',title,re.I):continue
  y=year+(month<dt.date.today().month-2)
  try: date=dt.date(y,month,day).isoformat()
  except ValueError:continue
  ev=record(date,title,'Bonanzbar',base)
  if ev:out.append(ev)
 return out
def parse_stellwerk(soup,base):
 out=[];text=soup.get_text(' ',strip=True); start=dt.date.today();year=start.year
 # dates are table cells in concert table; fallback regex around concert section
 for tr in soup.find_all('tr'):
  cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
  joined=' | '.join(cells)
  m=re.search(r'(\d{1,2})\.\s*(Jan|Feb|Mär|Mar|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?',joined,re.I)
  if not m:continue
  mon=MONTHS[m[2].lower()[:3]];y=year+(mon < start.month-2)
  try:date=dt.date(y,mon,int(m[1])).isoformat()
  except ValueError:continue
  title=next((x for x in cells if x and not re.search(r'^([A-Za-z]{2,3}\.?)$|\d{1,2}\.\s*\w+',x)), '')
  ev=record(date,title,'Stellwerk Schelklingen',base) if title else None
  if ev:out.append(ev)
 return out
def parse_roxy(soup,base):
 out=[]
 # ROXY detail links carry genre in link text and dates in surrounding cards. site-specific parser can be extended.
 for a in soup.find_all('a',href=True):
  href=a['href'];title=a.get_text(' ',strip=True)
  if not title or len(title)<8 or len(title)>190 or not ('/programm/' in href):continue
  node=a
  for _ in range(5):
   node=node.parent
   if not node:break
   text=node.get_text(' ',strip=True)
   m=re.search(r'\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})\b',text)
   month=re.search(r'(JANUAR|FEBRUAR|MÄRZ|APRIL|MAI|JUNI|JULI|AUGUST|SEPTEMBER|OKTOBER|NOVEMBER|DEZEMBER)\s+(20\d\d)',soup.get_text(' ',strip=True)[:200],re.I)
   months_full=['januar','februar','märz','april','mai','juni','juli','august','september','oktober','november','dezember']
   if m and month:
    try:date=dt.date(int(month[2]),months_full.index(month[1].lower())+1,int(m[1])).isoformat()
    except ValueError:break
    tm=re.search(r'\b(\d\d:\d\d)\s*H',text)
    ev=record(date,title,'ROXY Ulm',urljoin(base,href),tm[1] if tm else '')
    if ev:out.append(ev)
    break
 return out
def run():
 report=[];found=[]
 for name,url in load_sources():
  try:
   # Month-based venue pages for ROXY and Pauluskirche
   urls=[url]
   if name=='ROXY Ulm':
    today=dt.date.today();urls=[]
    for k in range(3):
     y=today.year+(today.month-1+k)//12;m=(today.month-1+k)%12+1
     urls.append(f'{url}?j={y}&m={m}')
   if name=='Pauluskirche':
    today=dt.date.today();urls=[]
    for k in range(3):
     y=today.year+(today.month-1+k)//12;m=(today.month-1+k)%12+1
     urls.append(f'{url}?month={y}{m:02d}')
   results=[]
   for u in urls:
    soup=fetch(u);results+=ld_events(soup,name,u)
    if name=='GOLD':results+=parse_gold(soup,u)
    elif name=='Bonanzbar':results+=parse_bonanz(soup,u)
    elif name=='Stellwerk Schelklingen':results+=parse_stellwerk(soup,u)
    elif name=='ROXY Ulm':results+=parse_roxy(soup,u)
   count=len(results);found+=results
   report.append(dict(name=name,url=url,state='ok' if count else 'needs_parser',count=count,note='' if count else 'Seite erreichbar, aber keine zuverlässig erkannten zukünftigen Termine'))
  except Exception as exc:
   report.append(dict(name=name,url=url,state='error',count=0,note=str(exc)[:140]))
  time.sleep(.4)
 unique={}
 for e in found:unique[e['id']]=e
 # Existing data is not silently carried forward as current after a scrape failure.
 payload=dict(generatedAt=dt.datetime.now(dt.timezone.utc).isoformat(),events=sorted(unique.values(),key=lambda x:(x['date'],x['time'],x['title'])),sources=report)
 (ROOT/'events.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Retrieved',len(unique),'events;',len([x for x in report if x['state']=='ok']),'sources with events')
 for x in report:print(x['name'],x['state'],x['count'])
if __name__=='__main__':run()

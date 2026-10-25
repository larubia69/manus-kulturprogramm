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
SKIP=re.compile(r'kino|kinofilm|filmvorführung|familienkonzert|kinder|familienprogramm|kids\b|jugendtheater|geschlossene gesellschaft|privatveranstaltung|kurzfilm|filmfestival|filmabend|wochenmarkt|gottesdienst|kindertheater|puppentheater|kasperle|kinderfest',re.I)
def clean_text(value):
 """Decode nested HTML entities and remove HTML tags from event text."""
 text=str(value or '')
 for _ in range(4):
  decoded=html.unescape(text)
  if decoded==text:break
  text=decoded
 text=BeautifulSoup(text,'html.parser').get_text(' ',strip=True)
 return ' '.join(text.replace('\\n',' ').replace('\xa0',' ').split())

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

# Conservative site-specific importers. A missing date means no event is added.
def parse_villa_exhibitions(soup,base):
 out=[]
 for heading in soup.find_all(['h2','h3','h4']):
  name=clean_text(heading.get_text(' ',strip=True))
  if not name or name.lower() in ('programm','ausstellungen','konzerte'):continue
  parent=heading.parent
  context=clean_text(parent.get_text(' ',strip=True)) if parent else ''
  if not re.search(r'\d{2}\.\d{2}\.20\d{2}',context):
   context=clean_text(parent.parent.get_text(' ',strip=True))[:350] if parent and parent.parent else context
  m=re.search(r'(\d{2})\.(\d{2})\.(20\d{2})\s*[–—-]\s*(\d{2})\.(\d{2})\.(20\d{2})',context)
  if not m:continue
  try:start=dt.date(int(m[3]),int(m[2]),int(m[1]));end=dt.date(int(m[6]),int(m[5]),int(m[4]))
  except ValueError:continue
  if end<dt.date.today():continue
  # In the calendar, an ongoing exhibition is represented from today onward.
  display=max(start,dt.date.today())
  link=heading.find('a',href=True) or (parent.find('a',href=True) if parent else None)
  ev=record(display.isoformat(),name,'Villa Rot',urljoin(base,link['href']) if link else base,details=f'Ausstellung vom {start:%d.%m.%Y} bis {end:%d.%m.%Y}; Öffnungszeiten auf der Originalseite.',genre='Kunst',end=end.isoformat())
  if ev:out.append(ev)
 return out

def parse_paulus(soup,base,year,month):
 out=[]
 # Calendar table cells start with day of month and contain event links.
 for td in soup.select('td'):
  text=clean_text(td.get_text(' ',strip=True))
  m=re.match(r'^(\d{1,2})(?!\d)',text)
  if not m:continue
  try:day=dt.date(year,month,int(m[1])).isoformat()
  except ValueError:continue
  for a in td.find_all('a',href=True):
   title=clean_text(a.get_text(' ',strip=True))
   if len(title)<5 or re.match(r'^\d+$',title):continue
   ev=record(day,title,'Pauluskirche',urljoin(base,a['href']),genre='Konzerte')
   if ev:out.append(ev)
 return out

def parse_roxy_v2(soup,base,year,month):
 out=[]
 # Event links are marked by their explicit genre on the programme page.
 genres={'Konzert':'Konzerte','Comedy':'Bühne','Kabarett':'Bühne','Theater':'Bühne','Bühne':'Bühne','Lesung':'Literatur','Party':'Club','Tanz':'Club','Treffpunkt':'Literatur'}
 heading_re=re.compile(r'^(Konzert|Comedy|Kabarett|Theater|Bühne|Lesung|Party|Tanz|Treffpunkt)\b',re.I)
 for a in soup.select('a[href]'):
  raw=clean_text(a.get_text(' ',strip=True))
  match=heading_re.match(raw)
  if not match or len(raw)<12:continue
  if re.search(r'familienkonzert|kinder|jugendmesse|ABGESAGT|verschoben',raw,re.I):continue
  label=match[1];title=raw[match.end():].strip(' –-')
  if len(title)<4:continue
  # Ascend to a local programme entry, accepting only a single unambiguous date.
  node=a; day=None;tm=''
  for _ in range(7):
   node=node.parent
   if not node:break
   t=clean_text(node.get_text(' ',strip=True))
   dates=re.findall(r'\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})(?=\s|$)',t)
   if len(set(dates))==1:
    day=int(dates[0]); times=re.findall(r'\b(\d{1,2}:\d{2})\s*H\b',t)
    if len(set(times))==1:tm=times[0]
    break
   if len(set(dates))>1:break
  if day is None:
   # ROXY often separates the weekday and day into adjacent HTML nodes.
   previous=[]
   for x in a.previous_elements:
    if isinstance(x,str):
     v=clean_text(x)
     if v:previous.append(v)
    if len(previous)>=90:break
   chronological=list(reversed(previous))
   for i in range(len(chronological)-2,-1,-1):
    token=chronological[i]
    if re.fullmatch(r'Mo|Di|Mi|Do|Fr|Sa|So',token):
     following=chronological[i+1]
     md=re.fullmatch(r'0?[1-9]|[12]\d|3[01]',following)
     if md:
      day=int(following)
      nearby=' '.join(chronological[i+2:])
      times=re.findall(r'\b(\d{1,2}:\d{2})\s*H\b',nearby)
      if times:tm=times[-1]
      break
   if day is None:continue
  try:date=dt.date(year,month,day).isoformat()
  except ValueError:continue
  ev=record(date,title,'ROXY Ulm',urljoin(base,a['href']),tm,genre=genres.get(label,'Konzerte'))
  if ev:out.append(ev)
 return out


# Additional importers: conservative extraction, dates required; false matches are skipped.
GERMAN_MONTHS={'januar':1,'februar':2,'maerz':3,'märz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12,
               'jan':1,'feb':2,'mär':3,'mar':3,'apr':4,'jun':6,'jul':7,'aug':8,'sep':9,'okt':10,'nov':11,'dez':12}

def upcoming_date(day,month,year=None):
 today=dt.date.today()
 if year is not None:
  try:return dt.date(int(year),int(month),int(day)).isoformat()
  except ValueError:return None
 for year_option in (today.year,today.year+1):
  try:candidate=dt.date(year_option,int(month),int(day))
  except ValueError:return None
  if candidate>=today-dt.timedelta(days=1):return candidate.isoformat()
 return None

def parse_rausgegangen(soup,base):
 """Read dated public event links, avoiding relative dates and undated recommendations."""
 out=[]
 # e.g. 'Fr, 06. Nov | 20:00 Mina Richman ... Aegis Café 23,00 €'
 pattern=re.compile(r'^(?:Mo|Di|Mi|Do|Fr|Sa|So),?\s+(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s*\|\s*(\d{1,2}:\d{2})\s+(.+)$',re.I)
 for a in soup.select('a[href]'):
  raw=clean_text(a.get_text(' ',strip=True))
  m=pattern.match(raw)
  if not m:continue
  mon=GERMAN_MONTHS.get(m[2].lower().rstrip('.'))
  if not mon:continue
  date=upcoming_date(m[1],mon)
  if not date:continue
  # On this aggregator, venue/price usually trail the title. Link destination supplies event details.
  # Prefer heading text for title when provided, otherwise strip trailing price/ticket information.
  title_node=a.find(['h2','h3','h4'])
  title=clean_text(title_node.get_text(' ',strip=True)) if title_node else m[4]
  title=re.split(r'\s+(?:ab|from)\s+\d+[,.]\d+\s*€|\s+\d+[,.]\d+\s*€|\s+Free admission\b',title,1,flags=re.I)[0]
  title=re.sub(r'\s+(?:WIN|PRESENTED)$','',title,flags=re.I).strip()
  # Without a distinct title node, this can include a venue name. Cap conservatively.
  if len(title)>120 or len(title)<5:continue
  url=urljoin(base,a['href'])
  if not url.startswith('https://rausgegangen.de/') or url.rstrip('/')==base.rstrip('/'):continue
  ev=record(date,title,'Rausgegangen Ulm',url,m[3],genre=category(title))
  if ev:out.append(ev)
 return out

def parse_livegigs(soup,base):
 """Find events with explicit year beside linked names in the venue overview."""
 out=[]
 # The page groups dates, artist links and categories in venue cards. Only extract
 # when a bounded card provides an unambiguous full date and event link.
 for a in soup.find_all('a',href=True):
  href=a['href']
  if not re.search(r'/events?/|/konzerte/|/gigs/',href,re.I):continue
  title=clean_text(a.get_text(' ',strip=True))
  if not 5<=len(title)<=105 or re.search(r'^(Tickets|Termine|Konzert|Details)$',title,re.I):continue
  parent=a
  for depth in range(1,5):
   parent=parent.parent
   if parent is None:break
   # Stop before a group of venues; never assign an adjacent venue's date.
   raw=clean_text(parent.get_text(' ',strip=True))
   if len(raw)>750:break
   m=re.search(r'\b(\d{1,2})\s*\.?\s*(Jan|Feb|Mär|Mar|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?\s*(20\d{2})\b',raw,re.I)
   if not m:continue
   month=MONTHS.get(m[2].lower()[:3]);date=upcoming_date(m[1],month,m[3]) if month else None
   if not date:break
   tm=re.search(r'\b(\d{1,2}:\d{2})\s*Uhr',raw,re.I)
   ev=record(date,title,'Livegigs Ulm',urljoin(base,href),tm[1] if tm else '')
   if ev:out.append(ev)
   break
 return out

def parse_birkenried(soup,base):
 """Only accept explicit Event schema from the embedded Eventfrog listing."""
 return ld_events(soup,'Birkenried',base)


# Additional source-specific readers. Prefer exact dates to guessing.
def parse_pfleghof(soup,base):
    result=[]
    # Langenau publishes each event as a date/time/title block. Read in document order.
    lines=[x.strip() for x in soup.get_text('\n',strip=True).splitlines() if x.strip()]
    date_re=re.compile(r'^(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?(?:\s*\([^)]*\))?,?\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b',re.I)
    for i,line in enumerate(lines):
        m=date_re.search(line)
        if not m:continue
        year=int(m[3]);year+=2000 if year<100 else 0
        try:day=dt.date(year,int(m[2]),int(m[1])).isoformat()
        except ValueError:continue
        window=lines[i+1:i+13]
        time_match=next((re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b',t) for t in window if re.search(r'\b([01]?\d|2[0-3]):[0-5]\d\b',t)),None)
        # Skip an optional end-date (for multi-day workshops) before the clock time.
        time_index=next((j for j,t in enumerate(window) if re.search(r'\b\d{1,2}:\d{2}\b',t)),None)
        if time_index is None:continue
        candidates=window[time_index+1:time_index+5]
        title=next((t for t in candidates if len(t)>3 and t.lower() not in ('image','veranstaltungsort:','veranstalter:') and not t.lower().startswith(('veranstaltungsort','veranstalter'))),None)
        if not title:continue
        desc=' '.join(window[time_index+2:time_index+5])
        if SKIP.search(title+' '+desc):continue
        # The source is a venue listing; ignore items whose named venue isn't Pfleghof.
        nearby=' '.join(window[:10]).lower()
        if 'veranstaltungsort:' in nearby and 'pfleghof' not in nearby and 'kultur' not in nearby:continue
        event=record(day,title,'Pfleghof Langenau',base,time_match.group(0) if time_match else '',desc)
        if event:result.append(event)
    return result

def parse_theater_ulm(soup,base):
    result=[]
    # Calendar entries: 'November 7 Samstag, 19:00 Uhr' followed by a stage and heading.
    full_months={'januar':1,'februar':2,'märz':3,'maerz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
    text=soup.get_text('\n',strip=True)
    # The page displays year in month navigation, and may span two calendar years.
    listed=re.findall(r'(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})',text,re.I)
    month_year={full_months[a.lower()]:int(b) for a,b in listed}
    for heading in soup.find_all(['h2','h3','h4']):
        title=heading.get_text(' ',strip=True)
        if not 3<len(title)<180 or SKIP.search(title):continue
        node=heading.parent
        for _ in range(4):
            if not node:break
            block=node.get_text(' ',strip=True)
            match=re.search(r'(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{1,2})\s+(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s*(\d{1,2}:\d{2})\s*Uhr',block,re.I)
            if match and len(block)<1200:
                month=full_months[match[1].lower()];year=month_year.get(month)
                if year is None:
                    now=dt.date.today();year=now.year+(month<now.month-2)
                try:date=dt.date(year,month,int(match[2])).isoformat()
                except ValueError:break
                href=heading.find('a',href=True) or node.find('a',href=True)
                link=urljoin(base,href['href']) if href else base
                label=block.lower()
                genre='Bühne' if any(k in label for k in ('schauspiel','tanztheater','musiktheater','oper','operette','ballett')) else 'Konzerte' if 'konzert' in label else category(title)
                ev=record(date,title,'Theater Ulm',link,match[3],genre=genre)
                if ev:result.append(ev)
                break
            node=node.parent
    return result

def run():
 report=[];found=[]
 for name,url in load_sources():
  try:
   # Month-based venue pages for ROXY and Pauluskirche
   urls=[url]
   if name=='Theater Ulm':
    urls=['https://www.theater-ulm.de/spielplan']
   if name=='Pfleghof Langenau':
    urls=['https://www.langenau.de/de/erleben/pfleghof/veranstaltung']
   if name=='Villa Rot':
    urls=['https://villa-rot.de/programm/ausstellungen/','https://villa-rot.de/programm/konzerte/','https://villa-rot.de/programm/veranstaltungen/']
   if name=='Birkenried':
    # Public Eventfrog embed used by the Birkenried dates page.
    try:
     main=fetch(url)
     embeds=[urljoin(url,x.get('src','')) for x in main.select('iframe[src]') if 'eventfrog' in x.get('src','').lower()]
     urls=[url]+embeds[:1]
    except requests.RequestException:pass
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
    try:soup=fetch(u)
    except requests.RequestException:
     if len(urls)>1:continue
     raise
    results+=ld_events(soup,name,u)
    if name=='GOLD':results+=parse_gold(soup,u)
    elif name=='Pfleghof Langenau':results+=parse_pfleghof(soup,u)
    elif name=='Theater Ulm':results+=parse_theater_ulm(soup,u)
    elif name=='Bonanzbar':results+=parse_bonanz(soup,u)
    elif name=='Stellwerk Schelklingen':results+=parse_stellwerk(soup,u)
    elif name=='ROXY Ulm':
     match=re.search(r'[?&]j=(\d{4})&m=(\d{1,2})',u)
     if match:results+=parse_roxy_v2(soup,u,int(match[1]),int(match[2]))
    elif name=='Villa Rot' and '/ausstellungen/' in u:results+=parse_villa_exhibitions(soup,u)
    elif name=='Rausgegangen Ulm':results+=parse_rausgegangen(soup,u)
    elif name=='Livegigs Ulm':results+=parse_livegigs(soup,u)
    elif name=='Birkenried':results+=parse_birkenried(soup,u)
    elif name=='Pauluskirche':
     match=re.search(r'month=(\d{4})(\d{2})',u)
     if match:results+=parse_paulus(soup,u,int(match[1]),int(match[2]))
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

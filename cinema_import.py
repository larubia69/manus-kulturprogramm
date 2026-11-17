#!/usr/bin/env python3
"""Mephisto / Obscura importer via cinema.de.

This currently imports the date explicitly printed on each cinema.de page.
It does not claim to import the full cinema week. Keeps prior data when a
request or parsing fails. Never imports other cinemas.
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CINEMAS = {
    'Mephisto Ulm': 'https://www.cinema.de/kino/kinoprogramm/ulm/mephisto',
    'Obscura Ulm': 'https://www.cinema.de/kino/kinoprogramm/ulm/obscura',
}
SOURCE_NAME = 'cinema.de (Mephisto & Obscura)'
DATE = re.compile(r'\bam\s+(\d{1,2})\.(\d{1,2})\.(20\d{2})\b', re.I)
TIME = re.compile(r'^(?:[01]?\d|2[0-3]):[0-5]\d$')


def parse_page(html, place, url, today=None):
    """Use the page's explicit schedule date, theater section, movie/time rows."""
    today = today or dt.date.today()
    soup = BeautifulSoup(html, 'html.parser')
    for el in soup(['script', 'style', 'noscript', 'nav', 'footer']):
        el.decompose()
    root = soup.find('main') or soup.body or soup
    strings = [s.strip() for s in root.stripped_strings if s.strip()]
    text = ' '.join(strings[:160])
    m = DATE.search(text)
    if not m:
        raise ValueError(f'Kein eindeutiges Programm-Datum auf {url}')
    date = dt.date(int(m[3]), int(m[2]), int(m[1]))
    if date < today or date > today + dt.timedelta(days=21):
        raise ValueError(f'Programm-Datum {date} liegt außerhalb des erlaubten Zeitfensters')
    expected = 'Mephisto' if place.startswith('Mephisto') else 'Obscura'
    # Start at the venue name *after* the timetable column headings, never
    # the venue label in page title or the search filter.
    heading_index = next((i for i in range(len(strings)-3)
                          if strings[i:i+4] == ['Kino','Film','Bewertung','Uhrzeit']), None)
    if heading_index is None:
        raise ValueError('Kinotabelle nicht gefunden (Seitenstruktur geändert)')
    idx = next((i for i in range(heading_index+4, len(strings))
                if strings[i].casefold() == expected.casefold()), None)
    if idx is None:
        raise ValueError(f'Keine {expected}-Einträge gefunden')
    out = []
    title = None
    stop_names = {'Mephisto', 'Obscura', 'Xinedome', 'Donau Film und Sterne'}
    for token in strings[idx+1:]:
        if token in stop_names or token in ('Filter zurücksetzen','Suchen'):
            break
        if TIME.fullmatch(token):
            if title:
                clock = token if len(token) == 5 else '0'+token
                key = f'{date}|{clock}|{place}|{title.casefold()}'
                out.append(dict(id=hashlib.sha256(key.encode()).hexdigest()[:16],
                                date=date.isoformat(), time=clock, title=title,
                                place=place, genre='Kino', url=url,
                                details='', end=None, source='cinema.de'))
            continue
        # A movie title usually precedes one or more times. Ignore purely
        # decorative fields, and do not silently guess if no film is present.
        if token and not token.isdigit() and len(token) < 200:
            title = token
    return list({(x['date'], x['time'], x['place'], x['title']): x for x in out}.values())


def run():
    path = ROOT / 'events.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    collected = []
    errors = []
    today = dt.date.today()
    for place, url in CINEMAS.items():
        try:
            resp = requests.get(url, timeout=18, headers={
                'User-Agent':'Mozilla/5.0 (compatible; ManusKulturprogramm/1.0)'})
            resp.raise_for_status()
            events = parse_page(resp.text, place, url, today)
            if not events:
                raise ValueError('Keine Filmzeiten erkannt')
            collected += events
            print(f'{place}: {len(events)} Vorstellungen am {events[0]["date"]}')
        except Exception as e:
            errors.append(f'{place}: {type(e).__name__}: {e}')
            print('Kinoquelle fehlgeschlagen:', errors[-1])
    existing = data.get('events', [])
    # Update only cinema dates/places actually retrieved; retain other venues
    # and do not delete anything if both sites fail.
    replaced = {(e['place'], e['date']) for e in collected}
    data['events'] = [e for e in existing if (e.get('place'), e.get('date')) not in replaced] + collected
    # Do not keep expired cinema screenings in current data.
    data['events'] = [e for e in data['events'] if e.get('genre') != 'Kino' or
                      (e.get('date') or '') >= today.isoformat()]
    previous = data.get('sources', [])
    old_names = {SOURCE_NAME, 'Cineplex Ulm (Mephisto & Obscura)'}
    data['sources'] = [x for x in previous if x.get('name') not in old_names] + [{
        'name':SOURCE_NAME, 'url':'https://www.cinema.de/kino/kinoprogramm/ulm',
        'state':'ok' if collected and not errors else ('partial' if collected else 'error'),
        'count':len(collected), 'note':'; '.join(errors)[:400]}]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Kinoimport cinema.de: {len(collected)} Vorstellungen, {len(errors)} Abruffehler')

if __name__ == '__main__':
    run()

#!/usr/bin/env python3
"""Mephisto/Obscura programme from cinema.de; conservative about stale dates.

Run after scraper.py; updates events.json without deleting other events.
Requires requests, beautifulsoup4 (already used by the main scraper).
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
VENUES = {
    'Mephisto Ulm': 'https://www.cinema.de/kino/kinoprogramm/ulm/mephisto',
    'Obscura Ulm': 'https://www.cinema.de/kino/kinoprogramm/ulm/obscura',
}
SOURCE_NAME = 'cinema.de (Mephisto & Obscura)'
DATE_PATTERN = re.compile(r'\bam\s+(\d{1,2})\.(\d{1,2})\.(20\d{2})\s*,\s*(Mephisto|Obscura)\b', re.I)
TIME_PATTERN = re.compile(r'^(?:[01]?\d|2[0-3]):[0-5]\d$')
IGNORE = {'Kino', 'Film', 'Bewertung', 'Uhrzeit', 'Mephisto', 'Obscura', 'Alle Filme',
          'Kinoprogramm', 'Suchen', 'Filter zurücksetzen'}


def parse_program(html, venue, source_url, today=None):
    today = today or dt.date.today()
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    lines = [re.sub(r'\s+', ' ', s).strip() for s in soup.get_text('\n', strip=True).splitlines()]
    lines = [line for line in lines if line]
    start_index = None
    for i, line in enumerate(lines):
        match = DATE_PATTERN.search(line)
        if match and match[4].casefold() == venue.split()[0].casefold():
            date = dt.date(int(match[3]), int(match[2]), int(match[1]))
            start_index = i
            break
    if start_index is None:
        raise ValueError('Kein eindeutiges Programm-Datum für '+venue)
    # A cinema.de page may show cached/outdated programme data. Do not misdate it.
    if date < today or date > today + dt.timedelta(days=14):
        raise ValueError(f'Programmdatum {date} ist nicht aktuell (heute {today})')

    # Start after the heading and table column labels, not the search filters.
    try:
        table_start = next(i for i in range(start_index+1, len(lines)) if lines[i].casefold() == 'uhrzeit') + 1
    except StopIteration:
        raise ValueError('Kinoprogramm-Tabelle nicht erkannt')
    if table_start < len(lines) and lines[table_start].casefold() == venue.split()[0].casefold():
        table_start += 1
    records = []
    current_title = None
    # The programme is a simple table with a film title followed by 1+ screening times.
    for line in lines[table_start:]:
        if DATE_PATTERN.search(line) or 'Alle Städte von A-Z' in line or 'Alle Filme von A-Z' in line:
            break
        if line in IGNORE or line.startswith('Kinoprogramm für'):
            continue
        if TIME_PATTERN.fullmatch(line):
            if current_title:
                screening_time = line if len(line)==5 else '0'+line
                key = '|'.join((date.isoformat(), screening_time, venue, current_title.casefold()))
                records.append({
                    'id': hashlib.sha256(key.encode('utf-8')).hexdigest()[:16],
                    'date': date.isoformat(), 'time': screening_time,
                    'title': current_title, 'place': venue, 'genre': 'Kino',
                    'url': source_url, 'details': '', 'end': None, 'source': SOURCE_NAME,
                })
        elif 2 <= len(line) <= 160 and not re.fullmatch(r'\d+', line):
            # Film titles are followed by times, and may contain punctuation/numbers.
            current_title = line
    if not records:
        raise ValueError('Keine Filmtitel mit Vorstellungszeiten erkannt')
    return list({(x['date'], x['time'], x['place'], x['title']): x for x in records}.values())


def run():
    path = ROOT / 'events.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    collected = []
    reports = []
    today = dt.date.today()
    for venue, url in VENUES.items():
        try:
            response = requests.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; ManusKulturprogramm/1.0)'}, timeout=18)
            response.raise_for_status()
            result = parse_program(response.text, venue, url, today)
            collected.extend(result)
            reports.append({'name': venue, 'url': url, 'state': 'ok', 'count': len(result)})
            print(f'{venue}: {len(result)} Vorstellungen ({result[0]["date"]})')
        except Exception as exc:
            print(f'{venue}: Import nicht bestätigt: {exc}')
            reports.append({'name': venue, 'url': url, 'state':'error', 'count':0, 'note':str(exc)[:180]})
    old = data.get('events', [])
    # Keep an existing cinema result for a cinema whose fetch failed, but drop dates in the past.
    successful_venues = {r['name'] for r in reports if r['state'] == 'ok'}
    new_events = [e for e in old if not (e.get('genre')=='Kino' and e.get('place') in successful_venues)]
    new_events = [e for e in new_events if not (e.get('genre') == 'Kino' and e.get('date', '') < today.isoformat())]
    new_events.extend(collected)
    data['events'] = new_events
    data['sources'] = [s for s in data.get('sources', []) if s.get('name') not in [SOURCE_NAME, 'Cineplex Ulm (Mephisto & Obscura)', *VENUES.keys()]] + reports
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Kinoimport cinema.de: {len(collected)} Vorstellungen, {sum(r["state"] == "error" for r in reports)} Abruffehler')


if __name__ == '__main__':
    run()

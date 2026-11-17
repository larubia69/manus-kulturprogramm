#!/usr/bin/env python3
"""Conservative cinema schedule importer: only Mephisto and Obscura (Ulm).
Writes events.json and reports failure without deleting existing entries.
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent
URL = 'https://www.cineplex.de/ulm/programm'
VENUES = {'mephisto': 'Mephisto Ulm', 'obscura': 'Obscura Ulm'}
DATE = re.compile(r'\b(?:MO|DI|MI|DO|FR|SA|SO)\s+(\d{1,2})\.(\d{1,2})\.?(?:\s*(20\d\d))?\b', re.I)
CLOCK = re.compile(r'\b(?:2D|3D|OV|OmU|DF|\S+)?\s*(\d{1,2}:\d{2})\b', re.I)


def date_iso(day, month, year=None, today=None):
    today = today or dt.date.today()
    if year:
        return dt.date(int(year), int(month), int(day)).isoformat()
    candidate = dt.date(today.year, int(month), int(day))
    if candidate < today - dt.timedelta(days=14):
        candidate = dt.date(today.year + 1, int(month), int(day))
    return candidate.isoformat()


def extract(html_text, today=None):
    today = today or dt.date.today()
    soup = BeautifulSoup(html_text, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    results = []
    seen_movies = set()
    film_links = soup.select('a[href*="/film/"]')
    for anchor in film_links:
        href = urljoin(URL, anchor.get('href', ''))
        title = ' '.join(anchor.get_text(' ', strip=True).split())
        # The main film header appears first, its detail/trailer links may repeat.
        if not (3 <= len(title) <= 140) or not re.search('/film/', href):
            continue
        # Film links can appear more than once (e.g. trailer), skip duplicates by URL.
        if href in seen_movies:
            continue
        seen_movies.add(href)
        tokens = []
        # Walk the document after the film link until next different film's link.
        # This avoids attaching screenings from neighbouring film cards.
        for node in anchor.next_elements:
            if isinstance(node, Tag) and node.name == 'a' and '/film/' in node.get('href', ''):
                nxt = urljoin(URL, node.get('href', ''))
                if nxt != href:
                    break
            if isinstance(node, NavigableString):
                token = ' '.join(str(node).split())
                if token:
                    tokens.append(token)
            if len(tokens) > 180:
                break
        curr_date = None
        curr_venue = None
        for token in tokens:
            m = DATE.search(token)
            if m:
                try:
                    curr_date = date_iso(m[1], m[2], m[3], today)
                except ValueError:
                    curr_date = None
                curr_venue = None
                continue
            # Only literal auditorium names qualify. Other Cineplex venues are excluded.
            vmatch = re.search(r'\bKino\s*\d+\s*,\s*(Mephisto|Obscura)\s+Ulm\b', token, re.I)
            if vmatch:
                curr_venue = VENUES[vmatch[1].lower()]
                continue
            if curr_date and curr_venue:
                tm = CLOCK.search(token)
                if not tm:
                    continue
                time = tm[1]
                if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time):
                    continue
                if dt.date.fromisoformat(curr_date) < today - dt.timedelta(days=1):
                    continue
                key = '|'.join([curr_date, time, curr_venue, title.casefold()])
                results.append(dict(
                    id=hashlib.sha256(key.encode()).hexdigest()[:16],
                    date=curr_date, time=time, title=title, place=curr_venue,
                    genre='Kino', url=href, details='', end=None,
                    source='Cineplex Ulm',
                ))
                curr_venue = None
    return list({(x['date'], x['time'], x['place'], x['title']): x for x in results}.values())


def run():
    path = ROOT / 'events.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    try:
        resp = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; ManusKulturprogramm/1.0)'}, timeout=20)
        resp.raise_for_status()
        movies = extract(resp.text)
        if not movies:
            raise ValueError('Keine vollständigen Kinovorstellungen erkannt; vorhandene Termine bleiben erhalten')
        # Remove old cinema results only after receiving a valid new programme.
        before = data.get('events', [])
        data['events'] = [e for e in before if not (e.get('genre') == 'Kino' and e.get('place') in VENUES.values())] + movies
        sources = [x for x in data.get('sources', []) if x.get('name') != 'Cineplex Ulm (Mephisto & Obscura)']
        sources.append({'name': 'Cineplex Ulm (Mephisto & Obscura)', 'url': URL, 'state': 'ok', 'count': len(movies)})
        data['sources'] = sources
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Cineplex: {len(movies)} Vorstellungen in Mephisto/Obscura importiert')
    except Exception as exc:
        sources = [x for x in data.get('sources', []) if x.get('name') != 'Cineplex Ulm (Mephisto & Obscura)']
        sources.append({'name': 'Cineplex Ulm (Mephisto & Obscura)', 'url': URL,
                        'state': 'error', 'count': 0, 'note': str(exc)[:200]})
        data['sources'] = sources
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Cineplex-Import nicht bestätigt: {exc}')


if __name__ == '__main__':
    run()

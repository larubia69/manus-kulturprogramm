#!/usr/bin/env python3
"""Normalize, classify and deduplicate multi-source programme entries.
Apply AFTER all event import steps, never before.
"""
import hashlib
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {'kultur in ulm', 'stadt ulm veranstaltungskalender', 'veranstaltungskalender ulm/neu-ulm',
           'eventim ulm', 'eventim neu-ulm', 'rausgegangen ulm', 'livegigs ulm', 'donau 3 fm', 'was geht?',
           'ulmtickets'}
VENUES = {
    'theater ulm': 'Theater Ulm',
    'mephisto': 'Mephisto Ulm', 'mephisto ulm': 'Mephisto Ulm',
    'obscura': 'Obscura Ulm', 'obscura ulm': 'Obscura Ulm',
    'roxy': 'ROXY Ulm', 'roxy ulm': 'ROXY Ulm',
    'birkenried': 'Birkenried', 'kulturgewächshaus birkenried': 'Birkenried',
    'gold': 'GOLD', 'das gold': 'GOLD',
    'fiddler’s green pub': 'Fiddlers Green Pub', 'fiddlers green pub': 'Fiddlers Green Pub',
}
RULES = [
    ('Kino', r'\b(kino|filmvorführung|kinovorstellung|filmkunst|cineplex)\b'),
    ('Club', r'\b(party|dj|disco|clubnacht|dancefloor|tanzparty|rave|tanzen|nightlife)\b'),
    ('Kunst', r'\b(ausstellung|vernissage|galerie|kunstausstellung)\b'),
    ('Bühne', r'\b(theater|kabarett|comedy|schauspiel|improtheater|ballett|musical|oper|poetry\s*slam)\b'),
    ('Literatur', r'\b(lesung|buchvorstellung|literatur|vortrag|diskussion|stammtisch|podiumsgespräch|workshop)\b'),
]

def clean(text):
    text = str(text or '')
    for _ in range(4):
        newer = html.unescape(text)
        if newer == text: break
        text = newer
    text = re.sub(r'<[^>]*>', ' ', text)
    text = text.replace('\\n', ' ').replace('\\t', ' ')
    return ' '.join(text.split())

def normalize_title(s):
    s = unicodedata.normalize('NFKD', clean(s).casefold())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s*[–—-]\s*(tickets?|ausverkauft|jetzt buchen)\b.*$', '', s)
    s = re.sub(r'\b(tickets?|eintrittskarten|karten kaufen|live in concert)\b', '', s)
    return re.sub(r'[^\w]+', '', s)

def canonical_place(name):
    name = clean(name)
    return VENUES.get(name.casefold(), name)

def classify(e):
    place = canonical_place(e.get('place', ''))
    if place == 'Theater Ulm': return 'Bühne'
    if place in ('Mephisto Ulm', 'Obscura Ulm'): return 'Kino'
    title = clean(e.get('title', ''))
    for genre, pattern in RULES:
        if re.search(pattern, title, re.I): return genre
    # A previously explicitly assigned genre is preserved if plausible.
    given = clean(e.get('genre', ''))
    if given in ('Konzerte', 'Kunst', 'Bühne', 'Literatur', 'Club', 'Kino'):
        return given
    return 'Konzerte'

def same_event(a, b):
    if a['date'] != b['date'] or normalize_title(a['title']) != normalize_title(b['title']): return False
    ta, tb = a.get('time') or '', b.get('time') or ''
    if ta and tb and ta != tb: return False  # distinct screenings / performances
    pa, pb = a['place'].casefold(), b['place'].casefold()
    if pa == pb: return True
    # Aggressive merges across different physical locations can lose real events.
    # Only merge if one of the names is a generic aggregator and times don't conflict.
    return (pa in SOURCES or pb in SOURCES) and bool(ta or tb)

def choice_score(e):
    return (e['place'].casefold() not in SOURCES, bool(e.get('time')),
            bool(e.get('url')), len(e.get('details', '')))

def merge(a, b):
    winner, loser = (a, b) if choice_score(a) >= choice_score(b) else (b, a)
    winner = winner.copy()
    if not winner.get('time'): winner['time'] = loser.get('time', '')
    if not winner.get('details'): winner['details'] = loser.get('details', '')
    if not winner.get('url'): winner['url'] = loser.get('url', '')
    return winner

def dedup(events):
    groups = defaultdict(list)
    for raw in events:
        if not isinstance(raw, dict) or not raw.get('date') or not raw.get('title'): continue
        e = dict(raw)
        e['title'] = clean(e['title'])
        e['place'] = canonical_place(e.get('place', ''))
        e['details'] = clean(e.get('details', ''))
        e['time'] = clean(e.get('time', ''))
        e['genre'] = classify(e)
        group_key = (e['date'], normalize_title(e['title']))
        matches = groups[group_key]
        target = next((i for i, old in enumerate(matches) if same_event(old, e)), None)
        if target is None: matches.append(e)
        else: matches[target] = merge(matches[target], e)
    output = [e for group in groups.values() for e in group]
    for e in output:
        # Stable IDs across sources after normalization, cinema keeps showtimes apart.
        key = '|'.join([e['date'], normalize_title(e['title']), e['place'].casefold(), e.get('time') or ''])
        e['id'] = hashlib.sha256(key.encode()).hexdigest()[:16]
        e['genre'] = classify(e)
    return sorted(output, key=lambda e: (e['date'], e.get('time', ''), e['title']))

def run():
    path = ROOT / 'events.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    before = len(data.get('events', []))
    data['events'] = dedup(data.get('events', []))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Bereinigung: {before} → {len(data["events"])} Einträge ({before-len(data["events"])} Dubletten entfernt)')

if __name__ == '__main__': run()

# -*- coding: utf-8 -*-
# Quiet Hours of Faith - Shorts (regular verses + USA topical themes)
# Har video pehle PRIVATE upload hoti hai aur publishAt se tay waqt par khud public hoti hai.

import os, sys, json, random, subprocess, urllib.request, textwrap, re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- Settings ----------
TOTAL_SHORTS = int(os.environ.get('TOTAL_SHORTS', 4))      # din ki Shorts
TOPICAL_COUNT = int(os.environ.get('TOPICAL_COUNT', 2))    # inme se kitni USA-topical
SLOT_HOURS = sorted(int(x) for x in os.environ.get('SLOT_HOURS_UTC', '14,18,22,1').split(','))
VOICE = 'en-US-ChristopherNeural'
RATE = '-10%'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
USED_FILE = 'used_shorts.json'
SCHEDULE_FILE = 'schedule_shorts.json'
CTA = 'If this touched your heart, please subscribe, like, and share this with those you love.'

# ---------- Topical themes ----------
# Headline ka text video mein KABHI nahi aata. Sirf andaza lagate hain ke log kis cheez
# ke baare mein fikar mand hain, aur us fikar ke mutabiq Psalms ki aayat dikhate hain.
THEMES = {
    'economy': {
        'keys': ['economy', 'inflation', 'prices', 'jobs', 'layoff', 'recession', 'tariff', 'market',
                 'tax', 'rent', 'mortgage', 'unemployment', 'wages'],
        'hook': 'Worried about money and prices?',
        'refs': [(37, 19), (34, 10), (55, 22)],
        'queries': ['sunrise field', 'wheat field', 'morning light'],
        'tags': ['economy', 'finances', 'provision']},
    'politics': {
        'keys': ['election', 'congress', 'senate', 'president', 'vote', 'campaign', 'white house',
                 'government', 'shutdown', 'supreme court'],
        'hook': 'Tired of the noise in the news?',
        'refs': [(146, 3), (118, 8), (20, 7)],
        'queries': ['quiet lake', 'mountain peaceful', 'forest mist'],
        'tags': ['trust in god', 'peace', 'usa']},
    'weather': {
        'keys': ['hurricane', 'storm', 'wildfire', 'flood', 'tornado', 'earthquake', 'blizzard',
                 'snowstorm', 'heat wave', 'drought'],
        'hook': 'Facing a storm in your life?',
        'refs': [(46, 1), (57, 1), (91, 2)],
        'queries': ['storm clouds sunrise', 'ocean waves calm', 'rain nature'],
        'tags': ['storm', 'refuge', 'hope']},
    'health': {
        'keys': ['hospital', 'flu', 'virus', 'cancer', 'health', 'vaccine', 'outbreak', 'medicare'],
        'hook': 'Need healing and strength today?',
        'refs': [(147, 3), (103, 3), (30, 2)],
        'queries': ['sunlight forest', 'gentle stream', 'morning dew'],
        'tags': ['healing', 'health', 'strength']},
    'conflict': {
        'keys': ['war', 'conflict', 'ceasefire', 'military', 'troops', 'missile', 'tensions'],
        'hook': 'Praying for peace in a troubled world?',
        'refs': [(46, 9), (29, 11), (122, 6)],
        'queries': ['peaceful sky', 'calm sea', 'sunrise mountain'],
        'tags': ['peace', 'prayer', 'world']},
    'thanks': {
        'keys': ['thanksgiving', 'christmas', 'holiday', 'family', 'veterans day', 'new year'],
        'hook': 'Take a quiet moment to be thankful.',
        'refs': [(100, 4), (107, 1), (136, 1)],
        'queries': ['autumn leaves', 'warm sunset', 'candle light'],
        'tags': ['thanksgiving', 'gratitude', 'family']},
    # Jab headlines se koi theme na mile to yeh filler theme use hoti hai
    'uncertain': {
        'keys': [],
        'hook': 'Feeling anxious about tomorrow?',
        'refs': [(56, 3), (94, 19), (27, 1)],
        'queries': ['nature peaceful', 'calm lake', 'forest light'],
        'tags': ['anxiety', 'peace', 'trust']},
}

# Dukhad / hassas headlines ko skip karte hain (in par verse chipkana munasib nahi)
SENSITIVE = ['kill', 'shot', 'shooting', 'dead', 'death', 'dies', 'died', 'murder', 'attack', 'abuse',
             'suicide', 'crash', 'rape', 'victim', 'terror', 'massacre', 'stabbing', 'bomb', 'hostage',
             'missing child', 'abduct', 'trial']


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', path],
        stdout=subprocess.PIPE, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 25.0


def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)


# ---------- Bible data ----------
urllib.request.urlretrieve(
    'https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json', 'bible.json')
with open('bible.json', 'r', encoding='utf-8-sig') as f:
    psalms = json.load(f)[18]['chapters']

used = load_json(USED_FILE, [])


def get_verse(c, v):
    return psalms[c - 1][v - 1].replace('\n', ' ')


def random_verse():
    for _ in range(500):
        c = random.randint(0, len(psalms) - 1)
        v = random.randint(0, len(psalms[c]) - 1)
        key = f'{c + 1}:{v + 1}'
        text = psalms[c][v].replace('\n', ' ')
        if 80 < len(text) < 150 and key not in used:
            return c + 1, v + 1, text
    # sab use ho gaye to list reset
    used.clear()
    return random_verse()


# ---------- Topical themes selection ----------
def fetch_headlines():
    try:
        r = requests.get('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en',
                         timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        root = ET.fromstring(r.content)
        return [i.findtext('title', '') for i in root.iter('item')]
    except Exception as e:
        print('Headlines fetch fail:', e)
        return []


def pick_themes(n):
    counts = {}
    for h in fetch_headlines():
        low = h.lower()
        if any(re.search(r'\b' + s, low) for s in SENSITIVE):
            continue
        for name, t in THEMES.items():
            if any(re.search(r'\b' + k, low) for k in t['keys']):
                counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts, key=counts.get, reverse=True)[:n]
    if len(ranked) < n and 'uncertain' not in ranked:
        ranked.append('uncertain')
    print('Aaj ki themes:', ranked)
    return ranked[:n]


def pick_topical_verse(theme):
    refs = [r for r in THEMES[theme]['refs'] if f'{r[0]}:{r[1]}' not in used] or THEMES[theme]['refs']
    c, v = random.choice(refs)
    return c, v, get_verse(c, v)


# ---------- Schedule slots ----------
def next_slots(n):
    last = load_json(SCHEDULE_FILE, {}).get('last')
    floor = datetime.now(timezone.utc) + timedelta(hours=1)  # kam az kam 1 ghanta aage
    if last:
        floor = max(floor, datetime.fromisoformat(last))
    slots, day = [], floor.date()
    for d in range(0, 30):
        for h in SLOT_HOURS:
            t = datetime(day.year, day.month, day.day, h, 0, tzinfo=timezone.utc) + timedelta(days=d)
            if t > floor:
                slots.append(t)
    slots.sort()
    return slots[:n]


# ---------- Video builder ----------
def get_background(i, queries):
    api_key = os.environ['PIXABAY_API_KEY']
    for q in random.sample(queries, len(queries)) + ['nature peaceful']:
        try:
            res = requests.get('https://pixabay.com/api/videos/',
                               params={'key': api_key, 'q': q, 'video_type': 'film', 'per_page': 30},
                               timeout=30).json()
            hits = res.get('hits', [])
            random.shuffle(hits)
            for hit in hits:
                for size in ('large', 'medium', 'small'):
                    u = hit['videos'].get(size, {}).get('url')
                    if u:
                        run(['curl', '-L', '-s', '-o', f'bg{i}.mp4', u])
                        return
        except Exception as e:
            print('Pixabay fail:', q, e)
    raise RuntimeError('Background video nahi mili')


def get_music():
    if os.path.exists('assets/music.mp3'):
        return 'assets/music.mp3'
    if not os.path.exists('music.mp3'):
        try:
            run(['curl', '-L', '-s', '-f', '-o', 'music.mp3',
                 'https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=relaxing-piano-music-amp-essential-music-11040.mp3'])
        except Exception:
            print('Music download fail, khamoshi use ho rahi hai')
            run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', '10', 'music.mp3'])
    return 'music.mp3'


def build_short(i, ref, verse, hook, queries):
    get_background(i, queries)
    music = get_music()

    with open(f'verse_{i}.txt', 'w', encoding='utf-8') as f:
        f.write(f'{textwrap.fill(verse, width=30)}\n\n- {ref}')
    with open(f'cta_{i}.txt', 'w', encoding='utf-8') as f:
        f.write('Subscribe, Like and\nShare with loved ones.')

    script = (f'{hook} ' if hook else '') + f'{verse}. {ref}. {CTA}'
    run(['edge-tts', '--text', script, '--voice', VOICE, f'--rate={RATE}',
         '--write-media', f'voice_{i}.mp3'])
    total = duration(f'voice_{i}.mp3')
    cta_start = f'{max(0, total - 7):.2f}'

    dt = (f'fontfile={FONT}:fontcolor=white:fontsize=55:box=1:boxcolor=black@0.7:boxborderw=25:'
          f'line_spacing=15:x=(w-text_w)/2:y=(h-text_h)/2')
    vf = (f'[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
          f'drawtext={dt}:textfile=verse_{i}.txt:enable=\'lt(t,{cta_start})\'')
    if hook:
        with open(f'hook_{i}.txt', 'w', encoding='utf-8') as f:
            f.write(textwrap.fill(hook, width=24))
        vf += (f',drawtext=fontfile={FONT}:textfile=hook_{i}.txt:fontcolor=yellow:fontsize=58:box=1:'
               f'boxcolor=black@0.7:boxborderw=20:line_spacing=12:x=(w-text_w)/2:y=200:'
               f'enable=\'lt(t,{cta_start})\'')
    vf += (f',drawtext=fontfile={FONT}:textfile=cta_{i}.txt:fontcolor=yellow:fontsize=60:box=1:'
           f'boxcolor=black@0.8:boxborderw=25:line_spacing=15:x=(w-text_w)/2:y=(h-text_h)/2:'
           f'enable=\'gte(t,{cta_start})\'[v]')
    af = '[2:a]volume=1.0[voice];[1:a]volume=0.2[bg];[voice][bg]amix=inputs=2:duration=first[aout]'

    out = f'short_{i}.mp4'
    run(['ffmpeg', '-y', '-stream_loop', '-1', '-i', f'bg{i}.mp4', '-stream_loop', '-1', '-i', music,
         '-i', f'voice_{i}.mp3', '-filter_complex', vf + ';' + af,
         '-map', '[v]', '-map', '[aout]', '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac',
         '-t', f'{total:.2f}', '-pix_fmt', 'yuv420p', out])
    return out


# ---------- Upload (private + publishAt) ----------
def get_youtube():
    secrets = json.loads(os.environ['CLIENT_SECRET_JSON'])
    sec = secrets.get('web') or secrets.get('installed') or {}
    creds = Credentials(
        token=None, refresh_token=os.environ['REFRESH_TOKEN'],
        token_uri='https://oauth2.googleapis.com/token',
        client_id=sec.get('client_id'), client_secret=sec.get('client_secret'),
        scopes=['https://www.googleapis.com/auth/youtube.upload'])
    return build('youtube', 'v3', credentials=creds)


def upload(youtube, path, title, desc, tags, publish_at):
    body = {
        'snippet': {'title': title[:100], 'description': desc, 'tags': tags, 'categoryId': '22'},
        'status': {
            'privacyStatus': 'private',                       # pehle hamesha private
            'publishAt': publish_at.strftime('%Y-%m-%dT%H:%M:%SZ'),  # phir tay waqt par khud public
            'selfDeclaredMadeForKids': False
        }
    }
    media = MediaFileUpload(path, chunksize=-1, resumable=True)
    resp = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    return resp['id']


# ---------- Main ----------
REGULAR_TITLES = ['{ref} | A Verse for Your Heart #Shorts',
                  '{ref} - Peace in His Presence #Shorts',
                  '{ref} | Quiet Moment With God #Shorts',
                  '{ref} - Words of Comfort #Shorts']

themes = pick_themes(TOPICAL_COUNT) if TOPICAL_COUNT > 0 else []
slots = next_slots(TOTAL_SHORTS)

order, reg, t = [], TOTAL_SHORTS - len(themes), list(themes)
for i in range(TOTAL_SHORTS):
    if (i % 2 == 1 and t) or reg == 0:
        order.append(('topical', t.pop(0)))
    else:
        order.append(('regular', None))
        reg -= 1

youtube = get_youtube()
failed = 0
for i, (kind, theme) in enumerate(order):
    try:
        if kind == 'topical':
            c, v, verse = pick_topical_verse(theme)
            th = THEMES[theme]
            hook, queries = th['hook'], th['queries']
            tags = ['bible', 'psalms', 'faith', 'christian', 'shorts', 'usa'] + th['tags']
            ref = f'Psalm {c}:{v}'
            title = f'{hook} {ref} #Shorts'
            desc = f'{hook}\n\n{ref} - {verse}\n\nA quiet word for anxious times. Share this with someone who needs it.'
        else:
            c, v, verse = random_verse()
            hook, queries = '', ['nature peaceful', 'forest mist', 'calm lake', 'mountain sunrise']
            ref = f'Psalm {c}:{v}'
            tags = ['bible', 'jesus', 'peace', 'shorts', 'christian', 'faith', 'psalms']
            title = random.choice(REGULAR_TITLES).format(ref=ref)
            desc = f'{ref} - {verse}\n\nShare this message.'

        video = build_short(i, ref, verse, hook, queries)
        vid = upload(youtube, video, title, desc, tags, slots[i])
        print(f'[{kind}] {ref} uploaded PRIVATE, public hogi: {slots[i].isoformat()} | ID: {vid}')

        used.append(f'{c}:{v}')
        save_json(USED_FILE, used)
        save_json(SCHEDULE_FILE, {'last': slots[i].isoformat()})
    except Exception as e:
        failed += 1
        print(f'Short {i} FAIL:', e)

if failed:
    sys.exit(1)

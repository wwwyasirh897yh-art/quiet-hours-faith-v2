# -*- coding: utf-8 -*-
# Quiet Hours of Faith - Long video (test version)
# Psalms KJV reading, calm nature visuals, 16:9, default upload = private

import os, json, random, subprocess, urllib.request, textwrap, math
from datetime import datetime, timedelta, timezone
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- Settings (yahan se tweak karo) ----------
TARGET_WORDS = int(os.environ.get('TARGET_WORDS', 1000))  # ~7-9 min video
MAX_WORDS = 1900                                           # ~15 min se zyada na ho
VOICE = 'en-US-ChristopherNeural'
RATE = '-15%'                                              # aahista, sukoon wali awaz
PRIVACY = os.environ.get('PRIVACY', 'private')             # private / unlisted / public
PUBLISH_AT = os.environ.get('PUBLISH_AT', '').strip()      # jaise 2026-11-10T17:00:00Z (UTC)
LONG_SLOT_HOUR_UTC = os.environ.get('LONG_SLOT_HOUR_UTC', '').strip()  # cron runs ke liye
if not PUBLISH_AT and LONG_SLOT_HOUR_UTC:
    _now = datetime.now(timezone.utc) + timedelta(hours=3)
    _t = _now.replace(hour=int(LONG_SLOT_HOUR_UTC), minute=0, second=0, microsecond=0)
    if _t <= _now:
        _t += timedelta(days=1)
    PUBLISH_AT = _t.strftime('%Y-%m-%dT%H:%M:%SZ')
USED_FILE = 'used_long.json'                               # repeat se bachne ke liye
W, H, FPS = 1920, 1080, 30
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', path],
        stdout=subprocess.PIPE, text=True, check=True)
    return float(r.stdout.strip())


# ---------- 1. Psalms text ----------
urllib.request.urlretrieve(
    'https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json',
    'bible.json')
with open('bible.json', 'r', encoding='utf-8-sig') as f:
    bible = json.load(f)
psalms = bible[18]['chapters']  # index 18 = Psalms

# Psalm 119 bohat lamba hai, usay chhor dete hain
allowed = [i for i in range(len(psalms)) if i != 118]

used = []
if os.path.exists(USED_FILE):
    with open(USED_FILE, 'r') as f:
        used = json.load(f)
fresh = [i for i in allowed if i not in used] or allowed  # sab use ho gaye to dobara shuru

start = random.choice(fresh)
chosen, words, idx = [], 0, start
while idx in allowed and idx < len(psalms):
    ch_text = ' '.join(v.replace('\n', ' ') for v in psalms[idx])
    ch_words = len(ch_text.split())
    if chosen and words + ch_words > MAX_WORDS:
        break
    chosen.append(idx)
    words += ch_words
    idx += 1
    if words >= TARGET_WORDS:
        break

first, last = chosen[0] + 1, chosen[-1] + 1
label = f'Psalm {first}' if first == last else f'Psalms {first}-{last}'

lines = []
for ci in chosen:
    lines.append(f'Psalm {ci + 1}.')
    for v in psalms[ci]:
        lines.append(v.replace('\n', ' '))
    lines.append('')
with open('script.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'{label} | words: {words}')

# ---------- 2. Voice ----------
run(['edge-tts', '--file', 'script.txt', '--voice', VOICE,
     f'--rate={RATE}', '--write-media', 'voice.mp3'])
voice_dur = duration('voice.mp3')
total = voice_dur + 6  # shuru mein 2 sec, aakhir mein 4 sec khamoshi
print(f'Voice duration: {voice_dur / 60:.1f} min')

# ---------- 3. Background clips (Pixabay) ----------
api_key = os.environ['PIXABAY_API_KEY']
queries = ['nature peaceful', 'forest mist', 'ocean waves calm', 'mountain sunrise',
           'river stream', 'clouds sky', 'lake morning', 'waterfall nature']
random.shuffle(queries)
urls = []
for q in queries[:3]:
    try:
        res = requests.get('https://pixabay.com/api/videos/',
                           params={'key': api_key, 'q': q, 'video_type': 'film', 'per_page': 20},
                           timeout=30).json()
        for hit in res.get('hits', []):
            for size in ('large', 'medium', 'small'):
                u = hit['videos'].get(size, {}).get('url')
                if u:
                    urls.append(u)
                    break
    except Exception as e:
        print('Pixabay query fail:', q, e)
random.shuffle(urls)
urls = list(dict.fromkeys(urls))[:6]
if not urls:
    raise SystemExit('Koi Pixabay video nahi mili, API key check karo')

clips = []
for n, u in enumerate(urls):
    raw, out = f'raw{n}.mp4', f'clip{n}.mp4'
    try:
        run(['curl', '-L', '-s', '-o', raw, u])
        run(['ffmpeg', '-y', '-i', raw, '-an',
             '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}',
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', out])
        clips.append((out, duration(out)))
    except Exception as e:
        print('Clip skip:', u, e)
if not clips:
    raise SystemExit('Koi clip process nahi hui')

cycle = sum(d for _, d in clips)
repeats = math.ceil(total / cycle) + 1
with open('concat.txt', 'w') as f:
    for _ in range(repeats):
        for name, _d in clips:
            f.write(f"file '{name}'\n")

# ---------- 4. Music ----------
music = 'assets/music.mp3'  # repo mein apna mp3 rakh do to yehi use hoga
if not os.path.exists(music):
    music = 'music.mp3'
    try:
        run(['curl', '-L', '-s', '-f', '-o', music,
             'https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=relaxing-piano-music-amp-essential-music-11040.mp3'])
    except Exception:
        print('Music download fail, khamoshi use ho rahi hai')
        run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-t', '10', music])

# ---------- 5. Title card text ----------
with open('title_cap.txt', 'w', encoding='utf-8') as f:
    f.write(textwrap.fill(label, 30) + '\n\nKing James Version')

# ---------- 6. Final render ----------
t_str = f'{total:.2f}'
fade_out_start = f'{total - 4:.2f}'
vfilter = (
    f'[0:v]fade=t=in:st=0:d=3,fade=t=out:st={fade_out_start}:d=4,'
    f'drawtext=fontfile={FONT}:textfile=title_cap.txt:fontcolor=white:fontsize=70:'
    f'box=1:boxcolor=black@0.55:boxborderw=30:line_spacing=15:'
    f'x=(w-text_w)/2:y=(h-text_h)/2:enable=\'between(t,2,10)\'[v]'
)
afilter = (
    '[2:a]adelay=2000|2000[voice];[1:a]volume=0.12[bg];'
    f'[voice][bg]amix=inputs=2:duration=longest:normalize=0,afade=t=out:st={fade_out_start}:d=4[aout]'
)
run(['ffmpeg', '-y',
     '-f', 'concat', '-safe', '0', '-i', 'concat.txt',
     '-stream_loop', '-1', '-i', music,
     '-i', 'voice.mp3',
     '-filter_complex', vfilter + ';' + afilter,
     '-map', '[v]', '-map', '[aout]',
     '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p',
     '-c:a', 'aac', '-b:a', '160k', '-t', t_str, 'final_long.mp4'])
print('Video ready. Size MB:', round(os.path.getsize('final_long.mp4') / 1e6, 1))

# ---------- 7. Upload ----------
secrets = json.loads(os.environ['CLIENT_SECRET_JSON'])
sec = secrets.get('web') or secrets.get('installed') or {}
creds = Credentials(
    token=None,
    refresh_token=os.environ['REFRESH_TOKEN'],
    token_uri='https://oauth2.googleapis.com/token',
    client_id=sec.get('client_id'),
    client_secret=sec.get('client_secret'),
    scopes=['https://www.googleapis.com/auth/youtube.upload'])
youtube = build('youtube', 'v3', credentials=creds)

title = f'{label} | Calm Bible Reading for Peace & Sleep (KJV)'[:100]
desc = (
    f'{label} read slowly in the King James Version, with calm nature scenes and soft piano.\n\n'
    'Let these words bring peace to your heart tonight.\n\n'
    'If this blessed you, please subscribe to Quiet Hours of Faith.\n\n'
    '#psalms #bible #peace #sleep #faith'
)
status_body = {'privacyStatus': PRIVACY, 'selfDeclaredMadeForKids': False}
if PUBLISH_AT:
    # Pehle private upload, phir tay waqt par khud public
    status_body['privacyStatus'] = 'private'
    status_body['publishAt'] = PUBLISH_AT
body = {
    'snippet': {
        'title': title,
        'description': desc,
        'tags': ['psalms', 'bible reading', 'kjv', 'sleep', 'peace', 'christian', 'faith'],
        'categoryId': '22'
    },
    'status': status_body
}
media = MediaFileUpload('final_long.mp4', chunksize=8 * 1024 * 1024, resumable=True)
request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f'Upload {int(status.progress() * 100)}%')
print('Long video uploaded! ID:', response['id'], '| privacy:', status_body['privacyStatus'], '| publishAt:', PUBLISH_AT or 'nahi')

# ---------- 8. Used list update ----------
used.extend(chosen)
with open(USED_FILE, 'w') as f:
    json.dump(used, f)

import os
import sys
import json
import math
import time
import wave
import random
import asyncio
import datetime
import traceback

import requests
import numpy as np
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, ImageClip, ColorClip, VideoClip, AudioFileClip,
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips, vfx,
)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------------------------------------------------------------
# 1. SETTINGS
# ---------------------------------------------------------------
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
CLIENT_SECRET_JSON = os.environ.get("CLIENT_SECRET_JSON")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
TOTAL_SHORTS = int(os.environ.get("TOTAL_SHORTS", 4))
SLOT_HOURS_UTC = [int(x) for x in os.environ.get("SLOT_HOURS_UTC", "14,18,22,1").split(",")]
SUBSCRIBE_OUTRO_SECONDS = float(os.environ.get("SUBSCRIBE_OUTRO_SECONDS", 6))
# Kam az kam total length (verse + reflection ki length is se zyada ho to video lambi ho jati hai)
TARGET_SHORT_SECONDS = float(os.environ.get("TARGET_SHORT_SECONDS", 25))
VOICE = os.environ.get("VOICE", "en-US-AriaNeural")
# Background music ki awaaz (0.08 = halki, 0.18 = tez)
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", 0.12))

USED_FILE = "used_shorts.json"
SCHEDULE_FILE = "schedule_shorts.json"

W, H, FPS = 1080, 1920, 24
OUTRO_LINE = "Subscribe for daily Psalms, and tap the bell."

# Har video ke shuru mein ek hook (random chuna jata hai)
HOOKS = [
    "If your heart feels heavy today, listen to this.",
    "Stop scrolling. God has a message for you.",
    "If you are tired and worried, this is for you.",
    "You are not forgotten. Listen closely.",
    "Before you sleep tonight, hear this.",
    "If you need peace right now, stay with me.",
    "This verse arrived for you today.",
    "When life feels too much, remember this.",
]

# Psalms (KJV): (reference, verse, short reflection)
PSALMS = [
    ("Psalm 23:1", "The Lord is my shepherd; I shall not want.",
     "A shepherd knows every sheep by name. Today, you are not forgotten and you are not alone. Rest in the thought that you are carefully watched over."),
    ("Psalm 23:4", "Yea, though I walk through the valley of the shadow of death, I will fear no evil: for thou art with me; thy rod and thy staff they comfort me.",
     "Notice that the verse says walk through the valley. Dark seasons are not where we stay. Keep walking, because you do not walk alone."),
    ("Psalm 27:1", "The Lord is my light and my salvation; whom shall I fear? the Lord is the strength of my life; of whom shall I be afraid?",
     "Fear gets quiet when we remember who stands beside us. Take one slow breath, and let that light be enough for the next step."),
    ("Psalm 30:5", "For his anger endureth but a moment; in his favour is life: weeping may endure for a night, but joy cometh in the morning.",
     "Some nights feel very long. But every night ends. If you are weeping tonight, hold on gently, because morning is already on its way."),
    ("Psalm 34:18", "The Lord is nigh unto them that are of a broken heart; and saveth such as be of a contrite spirit.",
     "When your heart feels broken, you are not far from help. God does not wait for you to be strong first. He comes close to the hurting."),
    ("Psalm 37:4", "Delight thyself also in the Lord; and he shall give thee the desires of thine heart.",
     "Delight comes before the desire. When we draw near to God with gladness, our wants slowly change, and our hearts become full."),
    ("Psalm 46:1", "God is our refuge and strength, a very present help in trouble.",
     "Look at the word present. Help is not far away or late. In the middle of today's trouble, a refuge is already open to you."),
    ("Psalm 46:10", "Be still, and know that I am God: I will be exalted among the heathen, I will be exalted in the earth.",
     "We spend so much time trying to control everything. For one quiet minute, put it all down. You do not have to hold the world together."),
    ("Psalm 51:10", "Create in me a clean heart, O God; and renew a right spirit within me.",
     "It is never too late for a fresh start. This simple prayer can be prayed again and again, whenever your heart feels tired."),
    ("Psalm 55:22", "Cast thy burden upon the Lord, and he shall sustain thee: he shall never suffer the righteous to be moved.",
     "You were never meant to carry every worry alone. Name your burden quietly, hand it over, and let your shoulders relax."),
    ("Psalm 56:3", "What time I am afraid, I will trust in thee.",
     "This verse does not say, I will never be afraid. It says, when I am afraid, I will trust. Courage is simply trusting while the fear is still there."),
    ("Psalm 62:1", "Truly my soul waiteth upon God: from him cometh my salvation.",
     "Waiting is hard in a world that rushes. But a soul that waits on God finds a deep peace that hurry can never give."),
    ("Psalm 91:1", "He that dwelleth in the secret place of the most High shall abide under the shadow of the Almighty.",
     "There is a quiet place where the noise of the world cannot reach you. It is found in prayer. Come back to it every day."),
    ("Psalm 91:11", "For he shall give his angels charge over thee, to keep thee in all thy ways.",
     "Even on days when you feel unseen, you are guarded. Each step you take today is watched over with great care."),
    ("Psalm 118:6", "The Lord is on my side; I will not fear: what can man do unto me?",
     "When you know who is on your side, other voices lose their power. Stand a little taller today, because you are not facing it alone."),
    ("Psalm 118:24", "This is the day which the Lord hath made; we will rejoice and be glad in it.",
     "Today is a gift that will never come again. Before the busyness begins, take a moment to simply say thank you."),
    ("Psalm 119:105", "Thy word is a lamp unto my feet, and a light unto my path.",
     "A lamp does not light the whole road, only the next few steps. That is enough. Faith is walking by the light we have today."),
    ("Psalm 121:1-2", "I will lift up mine eyes unto the hills, from whence cometh my help. My help cometh from the Lord, which made heaven and earth.",
     "When life feels heavy, lift your eyes. Our help does not come from our own strength, but from the One who made the heavens and the earth."),
    ("Psalm 147:3", "He healeth the broken in heart, and bindeth up their wounds.",
     "Healing is rarely quick, but it is tender. God does not rush your wounds. He binds them up slowly, with great care."),
    ("Psalm 16:11", "Thou wilt shew me the path of life: in thy presence is fulness of joy; at thy right hand there are pleasures for evermore.",
     "You do not need to see the whole path. You only need to stay close to the One who does. Joy is found in his presence."),
    ("Psalm 19:14", "Let the words of my mouth, and the meditation of my heart, be acceptable in thy sight, O Lord, my strength, and my redeemer.",
     "Before you speak today, pause. Let your words be kind, and let your thoughts be gentle. This small prayer can guide the whole day."),
]

BG_QUERIES = [
    "peaceful nature", "calm sky clouds", "sunrise mountains", "ocean waves calm",
    "forest light rays", "starry night sky", "calm lake", "golden hour field",
]

# ---------------------------------------------------------------
# 2. SMALL HELPERS
# ---------------------------------------------------------------
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def pill(d, box, fill, radius=None):
    """Safe rounded rectangle (integer coords, works on old Pillow)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x1 <= x0 or y1 <= y0:
        return
    r = (y1 - y0) // 2 if radius is None else int(radius)
    r = min(r, (x1 - x0) // 2, (y1 - y0) // 2)
    if r <= 0:
        d.rectangle((x0, y0, x1, y1), fill=fill)
        return
    d.rectangle((x0 + r, y0, x1 - r, y1), fill=fill)
    d.rectangle((x0, y0 + r, x1, y1 - r), fill=fill)
    for cx, cy in ((x0, y0), (x1 - 2 * r, y0), (x0, y1 - 2 * r), (x1 - 2 * r, y1 - 2 * r)):
        d.ellipse((cx, cy, cx + 2 * r, cy + 2 * r), fill=fill)


def circle(d, cx, cy, r, fill=None, outline=None, width=1):
    """Safe circle (integer coords)."""
    r = int(round(r))
    if r < 1:
        return
    cx, cy = int(round(cx)), int(round(cy))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=width)


FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


def load_font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, int(size))
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

# ---------------------------------------------------------------
# 3. YOUTUBE AUTH
# ---------------------------------------------------------------
def get_youtube_service():
    if not CLIENT_SECRET_JSON or not REFRESH_TOKEN:
        print("Missing YouTube credentials!")
        return None
    cfg = json.loads(CLIENT_SECRET_JSON)
    cfg = cfg.get("installed") or cfg.get("web")
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
    )
    return build("youtube", "v3", credentials=creds)

# ---------------------------------------------------------------
# 4. BACKGROUND (PIXABAY) + VOICE (EDGE-TTS)
# ---------------------------------------------------------------
def get_pixabay_video(path):
    if not PIXABAY_API_KEY:
        return None
    for q in random.sample(BG_QUERIES, 3):
        try:
            r = requests.get(
                "https://pixabay.com/api/videos/",
                params={"key": PIXABAY_API_KEY, "q": q, "video_type": "film",
                        "per_page": 20, "safesearch": "true"},
                timeout=30,
            )
            hits = r.json().get("hits", [])
            random.shuffle(hits)
            for hit in hits:
                v = hit.get("videos", {})
                url = (v.get("large") or {}).get("url") or (v.get("medium") or {}).get("url")
                if not url:
                    continue
                data = requests.get(url, timeout=120).content
                if data:
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
        except Exception as e:
            print(f"Pixabay error ({q}): {e}")
    return None


def tts_sync(text, filename, rate="-8%"):
    for attempt in range(3):
        try:
            asyncio.run(edge_tts.Communicate(text, VOICE, rate=rate).save(filename))
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return
        except Exception as e:
            print(f"TTS error (try {attempt + 1}): {e}")
        time.sleep(3)
    raise RuntimeError("TTS failed")

# ---------------------------------------------------------------
# 4b. BACKGROUND MUSIC (code khud generate karta hai: soft pad + halke piano notes)
# ---------------------------------------------------------------
def _mf(m):
    return 440.0 * 2 ** ((m - 69) / 12)


CHORDS = [
    [48, 55, 59, 64],   # Cmaj7
    [45, 55, 60, 64],   # Am7
    [41, 52, 57, 64],   # Fmaj7
    [43, 50, 59, 62],   # G
]


def generate_music(path, duration, sr=22050):
    n = int(duration * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    seg = 8.0
    shift = random.choice([-3, -2, 0, 2, 3])
    k, start = 0, 0.0
    while start < duration:
        chord = [m + shift for m in CHORDS[k % len(CHORDS)]]
        i0 = max(0, int((start - 1.5) * sr))
        i1 = min(n, int((start + seg + 1.5) * sr))
        tt = t[i0:i1] - start
        env = np.clip((tt + 1.5) / 3.0, 0, 1) * np.clip((seg + 1.5 - tt) / 3.0, 0, 1)
        env = env * env * (3 - 2 * env)
        pad = np.zeros_like(tt)
        for m in chord:
            f = _mf(m)
            pad += np.sin(2 * np.pi * f * tt)
            pad += 0.5 * np.sin(2 * np.pi * f * 1.003 * tt)
            pad += 0.25 * np.sin(2 * np.pi * f * 2 * tt)
        out[i0:i1] += pad * env * 0.06
        # halke piano jaise notes
        for j in range(4):
            pt = start + j * 2.0
            if pt >= duration:
                break
            f = _mf(random.choice(chord) + 12)
            j0 = int(pt * sr)
            j1 = min(n, j0 + int(3.0 * sr))
            if j1 <= j0:
                continue
            x = np.arange(j1 - j0) / sr
            note = (np.sin(2 * np.pi * f * x) * np.exp(-1.6 * x)
                    + 0.3 * np.sin(2 * np.pi * 2 * f * x) * np.exp(-3.0 * x))
            note *= np.clip(x / 0.01, 0, 1)
            out[j0:j1] += note * 0.22
        start += seg
        k += 1
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.9
    data = (np.stack([out, out], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return path

# ---------------------------------------------------------------
# 5. TEXT CARDS (hook card + verse card + reflection card)
# ---------------------------------------------------------------
def make_text_card(body, footer=None, header=None):
    n = len(body)
    size = 80 if n < 60 else 68 if n < 120 else 58 if n < 180 else 50
    font = load_font(size)
    small = load_font(46)
    tmp = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    lines = wrap_text(tmp, body, font, 880)
    lh = int(size * 1.4)
    pad = 60
    head_h = 80 if header else 0
    foot_h = 100 if footer else 0
    total = head_h + lh * len(lines) + foot_h
    top = (H - total) // 2 - 60

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pill(d, (60, top - pad, W - 60, top + total + pad), (0, 0, 0, 120), 40)

    y = top
    if header:
        w = d.textlength(header, font=small)
        x = (W - w) / 2
        d.text((x + 2, y + 2), header, font=small, fill=(0, 0, 0, 255))
        d.text((x, y), header, font=small, fill=(255, 215, 120, 255))
        y += head_h
    for line in lines:
        w = d.textlength(line, font=font)
        x = (W - w) / 2
        d.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 255))
        d.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += lh
    if footer:
        y += 40
        w = d.textlength(footer, font=small)
        x = (W - w) / 2
        d.text((x + 2, y + 2), footer, font=small, fill=(0, 0, 0, 255))
        d.text((x, y), footer, font=small, fill=(255, 215, 120, 255))
    return np.array(img)

# ---------------------------------------------------------------
# 6. SUBSCRIBE OUTRO (button + cursor click + bell click and ring)
# ---------------------------------------------------------------
_grad = np.zeros((H, W, 3), dtype=np.uint8)
_top, _bot = np.array([10, 14, 30]), np.array([34, 46, 92])
for _c in range(3):
    _grad[:, :, _c] = np.linspace(_top[_c], _bot[_c], H).astype(np.uint8)[:, None]
OUTRO_BASE = Image.fromarray(_grad, "RGB")

BG_FADE = (24, 34, 70)
WHITE = (255, 255, 255)
GOLD = (255, 215, 120)

BTN_CX, BTN_CY, BTN_W, BTN_H = 460, 1000, 460, 130
BELL_CX, BELL_CY = 785, 1000
CLICK1, CLICK2 = 1.9, 3.4          # subscribe click, bell click (seconds)
P0, PB, PL = (940, 1560), (530, 1030), (795, 1018)   # cursor: start, button, bell


def make_bell(angle=0.0, color=(255, 255, 255, 255), size=110):
    S = 220
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((98, 20, 122, 44), fill=color)                              # top knob
    d.ellipse((60, 36, 160, 136), fill=color)                             # dome
    d.polygon([(60, 86), (160, 86), (188, 164), (32, 164)], fill=color)   # body
    pill(d, (28, 158, 192, 180), color, 11)                               # rim
    d.ellipse((92, 176, 128, 208), fill=color)                            # clapper
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, center=(110, 22))
    return img.resize((int(size), int(size)), Image.LANCZOS)


def draw_cursor(img, x, y, scale=1.0):
    pts = [(0, 0), (0, 56), (14, 43), (25, 68), (36, 63), (26, 39), (45, 39)]
    pts = [(x + px * scale * 1.2, y + py * scale * 1.2) for px, py in pts]
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(255, 255, 255))
    d.line(pts + [pts[0]], fill=(0, 0, 0), width=3)


def cursor_pos(t):
    if t < 1.0:
        return P0
    if t < 1.8:
        k = smooth((t - 1.0) / 0.8)
        return (lerp(P0[0], PB[0], k), lerp(P0[1], PB[1], k))
    if t < 2.5:
        return PB
    if t < 3.3:
        k = smooth((t - 2.5) / 0.8)
        return (lerp(PB[0], PL[0], k), lerp(PB[1], PL[1], k))
    return PL


def bump(t, c, half=0.15):
    return max(0.0, 1.0 - abs(t - c) / half)


def render_outro_frame(t):
    img = OUTRO_BASE.copy()
    d = ImageDraw.Draw(img)

    # Title lines
    fade = smooth(t / 0.5)
    for text, size, color, cy in [
        ("Subscribe for", 92, WHITE, 480),
        ("daily Psalms", 92, GOLD, 600),
        ("and tap the bell", 56, (200, 200, 200), 740),
    ]:
        d.text((W // 2, cy), text, font=load_font(size),
               fill=lerp_color(BG_FADE, color, fade), anchor="mm")

    # Subscribe button (slides up, press effect, turns into SUBSCRIBED)
    if t >= 0.3:
        off = (1 - smooth((t - 0.3) / 0.7)) * 600
        press = 1 - 0.07 * bump(t, CLICK1)
        bw, bh = BTN_W * press, BTN_H * press
        cy = BTN_CY + off
        subscribed = t >= CLICK1 + 0.05
        fill = (70, 70, 70) if subscribed else (204, 0, 0)
        pill(d, (BTN_CX - bw / 2, cy - bh / 2, BTN_CX + bw / 2, cy + bh / 2), fill)
        d.text((int(BTN_CX), int(cy)), "SUBSCRIBED" if subscribed else "SUBSCRIBE",
               font=load_font(44), fill=WHITE, anchor="mm")

    # Bell (pops in, then click + ring)
    if t >= 2.4:
        bs = smooth((t - 2.4) / 0.35)
        bs = bs * (1 + 0.15 * math.sin(math.pi * bs))
        if bs > 0.02:
            clicked = t >= CLICK2 + 0.05
            circle(d, BELL_CX, BELL_CY, 65 * bs, fill=(80, 80, 80) if clicked else (60, 60, 60))
            angle = 0.0
            dt = t - (CLICK2 + 0.05)
            if 0 <= dt < 2.2:
                angle = 22 * math.sin(2 * math.pi * 2.6 * dt) * math.exp(-1.1 * dt)
            color = (255, 196, 0, 255) if clicked else (240, 240, 240, 255)
            size = max(8, int(110 * bs))
            bell = make_bell(angle=angle, color=color, size=size)
            img.paste(bell, (int(BELL_CX - size / 2), int(BELL_CY - size / 2 + 4)), bell)

    # Notifications label after bell click
    if t >= CLICK2 + 0.2:
        a = smooth((t - CLICK2 - 0.2) / 0.4)
        d.text((W // 2, 1180), "Notifications ON", font=load_font(46),
               fill=lerp_color(BG_FADE, GOLD, a), anchor="mm")

    # Click ripples
    for c, (cx, cy) in [(CLICK1, PB), (CLICK2, PL)]:
        dt = t - c
        if 0 <= dt < 0.5:
            rr = 20 + dt * 160
            col = lerp_color(WHITE, BG_FADE, dt / 0.5)
            circle(d, cx, cy, rr, outline=col, width=4)

    # Cursor
    if t >= 0.8:
        x, y = cursor_pos(t)
        s = 1 - 0.12 * max(bump(t, CLICK1), bump(t, CLICK2))
        draw_cursor(img, x, y, s)

    return np.array(img)

# ---------------------------------------------------------------
# 7. BUILD VIDEO
# ---------------------------------------------------------------
def build_background(bg_path, duration, keep):
    if bg_path:
        clip = VideoFileClip(bg_path, audio=False)
        keep.append(clip)
        cw = int(clip.h * W / H)
        if cw <= clip.w:
            clip = clip.crop(x_center=clip.w / 2, width=cw)
        else:
            ch = int(clip.w * H / W)
            clip = clip.crop(y_center=clip.h / 2, height=ch)
        clip = clip.resize((W, H))
        if clip.duration < duration:
            clip = clip.fx(vfx.loop, duration=duration)
        else:
            clip = clip.subclip(0, duration)
        return clip
    # Fallback: simple gradient if Pixabay fails
    return ImageClip(np.array(OUTRO_BASE)).set_duration(duration)


def create_video(idx, ref, verse, reflection, bg_path, voice_path, refl_path,
                 outro_voice_path, hook, hook_path):
    keep = []
    voice = AudioFileClip(voice_path)
    refl_voice = AudioFileClip(refl_path)
    outro_voice = AudioFileClip(outro_voice_path)
    hook_voice = AudioFileClip(hook_path)
    keep += [voice, refl_voice, outro_voice, hook_voice]
    vd, rd, hd = voice.duration, refl_voice.duration, hook_voice.duration

    outro_dur = max(SUBSCRIBE_OUTRO_SECONDS, outro_voice.duration + 0.6, 6.0)

    # Timeline: hook -> verse -> pause -> reflection -> pause -> outro
    hook_start = 0.3
    hook_end = hook_start + hd
    verse_start = hook_end + 0.8
    refl_start = verse_start + vd + 1.6
    content_end = refl_start + rd + 1.5
    main_dur = max(content_end, TARGET_SHORT_SECONDS - outro_dur)

    bg = build_background(bg_path, main_dur, keep)
    dim = ColorClip(size=(W, H), color=(0, 0, 0)).set_opacity(0.35).set_duration(main_dur)

    verse_card_start = hook_end + 0.4
    hook_card = (ImageClip(make_text_card(hook))
                 .set_start(0.1).set_duration(verse_card_start + 0.5 - 0.1)
                 .crossfadein(0.4).crossfadeout(0.5))
    verse_card = (ImageClip(make_text_card(verse, footer=ref))
                  .set_start(verse_card_start).set_duration(refl_start - verse_card_start + 0.5)
                  .crossfadein(1.0).crossfadeout(0.5))
    refl_card = (ImageClip(make_text_card(reflection, header="A quiet thought"))
                 .set_start(refl_start).set_duration(main_dur - refl_start)
                 .crossfadein(0.8))
    main_clip = CompositeVideoClip([bg, dim, hook_card, verse_card, refl_card],
                                   size=(W, H)).set_duration(main_dur)

    outro = VideoClip(render_outro_frame, duration=outro_dur)
    final = concatenate_videoclips([main_clip, outro])
    total = main_dur + outro_dur

    audio_parts = [
        hook_voice.set_start(hook_start),
        voice.set_start(verse_start),
        refl_voice.set_start(refl_start),
        outro_voice.set_start(main_dur + 0.5),
    ]

    # Background music (code se automatic generate, voice ke neeche halka)
    music_path = f"music_{idx}.wav"
    try:
        generate_music(music_path, total + 1)
        music = AudioFileClip(music_path)
        keep.append(music)
        music = (music.subclip(0, total).volumex(MUSIC_VOLUME)
                 .audio_fadein(1).audio_fadeout(2))
        audio_parts.insert(0, music)
    except Exception as e:
        print(f"Music generate nahi hui, bina music ke chal rahe hain: {e}")

    final = final.set_audio(CompositeAudioClip(audio_parts).set_duration(total))

    out = f"final_short_{idx}.mp4"
    final.write_videofile(
        out, fps=FPS, codec="libx264", audio_codec="aac", preset="veryfast", threads=2,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        temp_audiofile=f"temp_audio_{idx}.m4a", remove_temp=True, logger=None,
    )
    for c in keep:
        try:
            c.close()
        except Exception:
            pass
    try:
        final.close()
    except Exception:
        pass
    if os.path.exists(music_path):
        os.remove(music_path)
    return out

# ---------------------------------------------------------------
# 8. UPLOAD
# ---------------------------------------------------------------
def upload_video(youtube, video_file, title, description, publish_hour_utc):
    now = datetime.datetime.utcnow()
    publish_time = now.replace(hour=publish_hour_utc, minute=0, second=0, microsecond=0)
    if publish_time < now + datetime.timedelta(minutes=20):
        publish_time += datetime.timedelta(days=1)
    publish_str = publish_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["psalms", "bible", "faith", "kjv", "prayer", "shorts"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_str,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype="video/mp4")
    resp = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    print(f"Uploaded! Video ID: {resp['id']} | publish at {publish_str}")
    return resp["id"], publish_str

# ---------------------------------------------------------------
# 9. MAIN
# ---------------------------------------------------------------
def main():
    youtube = get_youtube_service()
    if not youtube:
        sys.exit(1)

    used = load_json(USED_FILE, [])
    if not isinstance(used, list):
        used = []

    # Purani file dict format main thi: usay mehfooz rakh kar "uploads" list add karte hain
    schedule = load_json(SCHEDULE_FILE, {})
    if not isinstance(schedule, dict):
        schedule = {"old_entries": schedule}
    if not isinstance(schedule.get("uploads"), list):
        schedule["uploads"] = []

    outro_voice_path = "outro_voice.mp3"
    tts_sync(OUTRO_LINE, outro_voice_path, rate="-5%")

    picked_now = []
    picked_hooks = []
    uploaded = 0

    for i in range(TOTAL_SHORTS):
        print(f"\n--- Creating Short {i + 1}/{TOTAL_SHORTS} ---")
        available = [p for p in PSALMS if p[0] not in used and p[0] not in picked_now]
        if not available:
            used = []
            available = [p for p in PSALMS if p[0] not in picked_now] or PSALMS
        ref, verse, reflection = random.choice(available)
        picked_now.append(ref)

        # Is run mein har Short ka hook alag rakhne ki koshish
        hook_choices = [h for h in HOOKS if h not in picked_hooks] or HOOKS
        hook = random.choice(hook_choices)
        picked_hooks.append(hook)

        bg_path = f"background_{i}.mp4"
        voice_path = f"voice_{i}.mp3"
        refl_path = f"reflection_{i}.mp3"
        hook_path = f"hook_{i}.mp3"
        video_path = None
        try:
            bg_path = get_pixabay_video(bg_path)
            spoken_ref = ref.replace(":", ", verse ")
            tts_sync(f"{verse} {spoken_ref}.", voice_path)
            tts_sync(reflection, refl_path, rate="-6%")
            tts_sync(hook, hook_path, rate="-8%")

            video_path = create_video(i, ref, verse, reflection, bg_path,
                                      voice_path, refl_path, outro_voice_path,
                                      hook, hook_path)

            hour = SLOT_HOURS_UTC[i % len(SLOT_HOURS_UTC)]
            snippet = verse[:50].rstrip(" ,;:.")
            title = f"{snippet}... ({ref}) #Shorts"
            desc = (f"{ref} (KJV)\n\n{verse}\n\n{reflection}\n\n"
                    "Subscribe for daily Psalms and tap the bell.\n\n"
                    "#Psalms #KJV #Faith #Shorts")

            vid, publish_str = upload_video(youtube, video_path, title, desc, hour)
            uploaded += 1

            # Upload ho chuki, ab tracking save karein (pehle used, phir schedule)
            used.append(ref)
            save_json(USED_FILE, used)
            try:
                schedule["uploads"].append({"video_id": vid, "ref": ref, "publish_at": publish_str})
                schedule["uploads"] = schedule["uploads"][-200:]
                save_json(SCHEDULE_FILE, schedule)
            except Exception as e:
                print(f"Schedule log save failed (upload theek hai): {e}")
        except Exception as e:
            traceback.print_exc()
            print(f"Short {i + 1} failed: {e}")
        finally:
            for p in (bg_path, voice_path, refl_path, hook_path, video_path):
                if p and os.path.exists(p):
                    os.remove(p)

    if os.path.exists(outro_voice_path):
        os.remove(outro_voice_path)

    print(f"\n--- Done: {uploaded}/{TOTAL_SHORTS} Shorts uploaded ---")
    if uploaded == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

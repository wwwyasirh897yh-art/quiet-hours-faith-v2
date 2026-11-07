import os
import sys
import json
import math
import time
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
TARGET_SHORT_SECONDS = float(os.environ.get("TARGET_SHORT_SECONDS", 25))
VOICE = os.environ.get("VOICE", "en-US-AriaNeural")

USED_FILE = "used_shorts.json"
SCHEDULE_FILE = "schedule_shorts.json"

W, H, FPS = 1080, 1920, 24
OUTRO_LINE = "Subscribe for daily Psalms, and tap the bell."

# Psalms (KJV)
PSALMS = [
    ("Psalm 23:1", "The Lord is my shepherd; I shall not want."),
    ("Psalm 23:4", "Yea, though I walk through the valley of the shadow of death, I will fear no evil: for thou art with me; thy rod and thy staff they comfort me."),
    ("Psalm 27:1", "The Lord is my light and my salvation; whom shall I fear? the Lord is the strength of my life; of whom shall I be afraid?"),
    ("Psalm 30:5", "For his anger endureth but a moment; in his favour is life: weeping may endure for a night, but joy cometh in the morning."),
    ("Psalm 34:18", "The Lord is nigh unto them that are of a broken heart; and saveth such as be of a contrite spirit."),
    ("Psalm 37:4", "Delight thyself also in the Lord; and he shall give thee the desires of thine heart."),
    ("Psalm 46:1", "God is our refuge and strength, a very present help in trouble."),
    ("Psalm 46:10", "Be still, and know that I am God: I will be exalted among the heathen, I will be exalted in the earth."),
    ("Psalm 51:10", "Create in me a clean heart, O God; and renew a right spirit within me."),
    ("Psalm 55:22", "Cast thy burden upon the Lord, and he shall sustain thee: he shall never suffer the righteous to be moved."),
    ("Psalm 56:3", "What time I am afraid, I will trust in thee."),
    ("Psalm 62:1", "Truly my soul waiteth upon God: from him cometh my salvation."),
    ("Psalm 91:1", "He that dwelleth in the secret place of the most High shall abide under the shadow of the Almighty."),
    ("Psalm 91:11", "For he shall give his angels charge over thee, to keep thee in all thy ways."),
    ("Psalm 118:6", "The Lord is on my side; I will not fear: what can man do unto me?"),
    ("Psalm 118:24", "This is the day which the Lord hath made; we will rejoice and be glad in it."),
    ("Psalm 119:105", "Thy word is a lamp unto my feet, and a light unto my path."),
    ("Psalm 121:1-2", "I will lift up mine eyes unto the hills, from whence cometh my help. My help cometh from the Lord, which made heaven and earth."),
    ("Psalm 147:3", "He healeth the broken in heart, and bindeth up their wounds."),
    ("Psalm 16:11", "Thou wilt shew me the path of life: in thy presence is fulness of joy; at thy right hand there are pleasures for evermore."),
    ("Psalm 19:14", "Let the words of my mouth, and the meditation of my heart, be acceptable in thy sight, O Lord, my strength, and my redeemer."),
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
# 5. VERSE TEXT IMAGE
# ---------------------------------------------------------------
def make_verse_image(verse, ref):
    n = len(verse)
    size = 80 if n < 60 else 68 if n < 120 else 58 if n < 180 else 50
    font = load_font(size)
    ref_font = load_font(48)
    tmp = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    lines = wrap_text(tmp, verse, font, 880)
    lh = int(size * 1.4)
    gap, ref_h, pad = 40, 60, 60
    total = lh * len(lines) + gap + ref_h
    top = (H - total) // 2 - 60

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pill(d, (60, top - pad, W - 60, top + total + pad), (0, 0, 0, 120), 40)

    y = top
    for line in lines:
        w = d.textlength(line, font=font)
        x = (W - w) / 2
        d.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 255))
        d.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += lh
    y += gap
    w = d.textlength(ref, font=ref_font)
    x = (W - w) / 2
    d.text((x + 2, y + 2), ref, font=ref_font, fill=(0, 0, 0, 255))
    d.text((x, y), ref, font=ref_font, fill=(255, 215, 120, 255))
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


def create_video(idx, ref, verse, bg_path, voice_path, outro_voice_path):
    keep = []
    voice = AudioFileClip(voice_path)
    outro_voice = AudioFileClip(outro_voice_path)
    keep += [voice, outro_voice]
    vd = voice.duration

    outro_dur = max(SUBSCRIBE_OUTRO_SECONDS, outro_voice.duration + 0.6, 6.0)
    main_dur = max(vd + 2.0, TARGET_SHORT_SECONDS - outro_dur)

    bg = build_background(bg_path, main_dur, keep)
    dim = ColorClip(size=(W, H), color=(0, 0, 0)).set_opacity(0.35).set_duration(main_dur)
    txt = (ImageClip(make_verse_image(verse, ref)).set_duration(main_dur - 0.2)
           .set_start(0.2).crossfadein(1.0))
    main_clip = CompositeVideoClip([bg, dim, txt], size=(W, H)).set_duration(main_dur)

    outro = VideoClip(render_outro_frame, duration=outro_dur)
    final = concatenate_videoclips([main_clip, outro])
    total = main_dur + outro_dur

    # Audio: verse (repeated if there is room) + outro voice
    parts, t = [], 0.8
    reps = 0
    while t + vd <= main_dur - 0.8 and reps < 3:
        parts.append(voice.set_start(t))
        t += vd + 3.0
        reps += 1
    if not parts:
        parts.append(voice.set_start(0.5))
    parts.append(outro_voice.set_start(main_dur + 0.5))
    final = final.set_audio(CompositeAudioClip(parts).set_duration(total))

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
    schedule = load_json(SCHEDULE_FILE, [])

    outro_voice_path = "outro_voice.mp3"
    tts_sync(OUTRO_LINE, outro_voice_path, rate="-5%")

    picked_now = []
    uploaded = 0

    for i in range(TOTAL_SHORTS):
        print(f"\n--- Creating Short {i + 1}/{TOTAL_SHORTS} ---")
        available = [p for p in PSALMS if p[0] not in used and p[0] not in picked_now]
        if not available:
            used = []
            available = [p for p in PSALMS if p[0] not in picked_now] or PSALMS
        ref, verse = random.choice(available)
        picked_now.append(ref)

        bg_path = f"background_{i}.mp4"
        voice_path = f"voice_{i}.mp3"
        video_path = None
        try:
            bg_path = get_pixabay_video(bg_path)
            spoken_ref = ref.replace(":", ", verse ")
            tts_sync(f"{verse} {spoken_ref}.", voice_path)

            video_path = create_video(i, ref, verse, bg_path, voice_path, outro_voice_path)

            hour = SLOT_HOURS_UTC[i % len(SLOT_HOURS_UTC)]
            snippet = verse[:50].rstrip(" ,;:.")
            title = f"{snippet}... ({ref}) #Shorts"
            desc = (f"{ref} (KJV)\n\n{verse}\n\n"
                    "Subscribe for daily Psalms and tap the bell.\n\n"
                    "#Psalms #KJV #Faith #Shorts")

            vid, publish_str = upload_video(youtube, video_path, title, desc, hour)
            used.append(ref)
            schedule.append({"video_id": vid, "ref": ref, "publish_at": publish_str})
            save_json(USED_FILE, used)
            save_json(SCHEDULE_FILE, schedule[-200:])
            uploaded += 1
        except Exception as e:
            traceback.print_exc()
            print(f"Short {i + 1} failed: {e}")
        finally:
            for p in (bg_path, voice_path, video_path):
                if p and os.path.exists(p):
                    os.remove(p)

    if os.path.exists(outro_voice_path):
        os.remove(outro_voice_path)

    print(f"\n--- Done: {uploaded}/{TOTAL_SHORTS} Shorts uploaded ---")
    if uploaded == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

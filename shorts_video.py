import os
import json
import asyncio
import datetime
import requests
import random
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import *
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. ENVIRONMENT VARIABLES ---
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
CLIENT_SECRET_JSON = os.environ.get("CLIENT_SECRET_JSON")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
TOTAL_SHORTS = int(os.environ.get("TOTAL_SHORTS", 4))
SLOT_HOURS_UTC = [int(x) for x in os.environ.get("SLOT_HOURS_UTC", "14,18,22,1").split(",")]
SUBSCRIBE_OUTRO_SECONDS = int(os.environ.get("SUBSCRIBE_OUTRO_SECONDS", 6))
TARGET_SHORT_SECONDS = int(os.environ.get("TARGET_SHORT_SECONDS", 46))

# --- 2. YOUTUBE AUTHENTICATION ---
def get_youtube_service():
    if not CLIENT_SECRET_JSON or not REFRESH_TOKEN:
        print("Missing YouTube Credentials!")
        return None
    
    client_config = json.loads(CLIENT_SECRET_JSON)['installed']
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_config['client_id'],
        client_secret=client_config['client_secret']
    )
    return build('youtube', 'v3', credentials=creds)

# --- 3. GET BACKGROUND FROM PIXABAY ---
def get_pixabay_video(query="faith peaceful nature"):
    url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}&video_type=film&per_page=10"
    response = requests.get(url).json()
    if response['hits']:
        video_url = random.choice(response['hits'])['videos']['large']['url']
        video_path = "background.mp4"
        with open(video_path, 'wb') as f:
            f.write(requests.get(video_url).content)
        return video_path
    return None

# --- 4. GENERATE AUDIO (TTS) ---
async def generate_audio(text, filename):
    voice = "en-US-AriaNeural" # Aap voice change kar sakte hain
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

# --- 5. CREATE VIDEO ---
def create_video(text, bg_path, audio_path):
    # Audio Load
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    
    # Background Load & Resize to 1080x1920 (Shorts)
    bg = VideoFileClip(bg_path).subclip(0, duration).resize(height=1920)
    bg = bg.crop(x_center=bg.w/2, width=1080)
    
    # Text Overlay (Centered)
    # Note: Aap apna custom font use kar sakte hain, yahan default use ho raha hai
    txt_clip = TextClip(text, fontsize=70, color='white', font='DejaVu-Sans-Bold', 
                        method='caption', size=(900, None), align='center')
    txt_clip = txt_clip.set_position('center').set_duration(duration)
    
    # Outro (Subscribe)
    outro_bg = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=SUBSCRIBE_OUTRO_SECONDS)
    outro_text = TextClip("Subscribe for more!\nLike & Share", fontsize=90, color='red', font='DejaVu-Sans-Bold')
    outro_text = outro_text.set_position('center').set_duration(SUBSCRIBE_OUTRO_SECONDS)
    outro = CompositeVideoClip([outro_bg, outro_text])
    
    # Combine Main Video + Outro
    final_video = CompositeVideoClip([bg, txt_clip])
    final_video = concatenate_videoclips([final_video, outro])
    final_video = final_video.set_audio(audio) # Outro ke liye alag audio bhi add kar sakte hain
    
    output_filename = "final_short.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
    
    # Cleanup
    audio.close()
    bg.close()
    final_video.close()
    return output_filename

# --- 6. UPLOAD TO YOUTUBE ---
def upload_video(youtube, video_file, title, description, publish_hour_utc):
    # Schedule time calculate karein (Aaj UTC time mein)
    now = datetime.datetime.utcnow()
    publish_time = now.replace(hour=publish_hour_utc, minute=0, second=0, microsecond=0)
    
    # Agar time nikal gaya hai, toh kal ka din set karein
    if publish_time < now:
        publish_time += datetime.timedelta(days=1)
    
    publish_time_str = publish_time.isoformat("T") + "Z"
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['faith', 'peace', 'shorts', 'islam', 'inspiration'],
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'private',
            'publishAt': publish_time_str,
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print(f"Uploaded Successfully! Video ID: {response['id']}")

# --- 7. MAIN LOGIC ---
def main():
    # Fake verses list (Aap isko apni marzi se expand kar sakte hain)
    verses = [
        "Trust in the Lord with all your heart.",
        "Peace begins with a smile.",
        "Be still, and know that I am God.",
        "Let your light shine before others.",
        "Faith over fear."
    ]

    youtube = get_youtube_service()
    if not youtube:
        return

    # JSON load karein purane shorts track karne ke liye
    used_file = "used_shorts.json"
    used_shorts = []
    if os.path.exists(used_file):
        with open(used_file, 'r') as f:
            used_shorts = json.load(f)

    # Videos generate loop
    for i in range(TOTAL_SHORTS):
        print(f"\n--- Creating Short {i+1}/{TOTAL_SHORTS} ---")
        
        # Random verse uthayein jo pehle use na hua ho
        available_verses = [v for v in verses if v not in used_shorts]
        if not available_verses:
            available_verses = verses # Agar sab use ho gaye toh reset
            used_shorts = []
            
        current_text = random.choice(available_verses)
        
        # 1. Assets generate karein
        bg_path = get_pixabay_video()
        audio_path = "voice.mp3"
        asyncio.run(generate_audio(current_text, audio_path))
        
        # 2. Video banayein
        video_path = create_video(current_text, bg_path, audio_path)
        
        # 3. Upload karein
        publish_hour = SLOT_HOURS_UTC[i] # Har video ka alag slot time
        title = f"{current_text[:40]}... #Shorts"
        desc = f"{current_text}\n\nSubscribe for daily peace!"
        
        try:
            upload_video(youtube, video_path, title, desc, publish_hour)
            used_shorts.append(current_text)
        except Exception as e:
            print(f"Upload Failed: {e}")
            
        # 4. Cleanup files for next loop
        if os.path.exists(bg_path): os.remove(bg_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(video_path): os.remove(video_path)

    # Update used_shorts.json
    with open(used_file, 'w') as f:
        json.dump(used_shorts, f, indent=4)
        
    print("\n--- All Shorts Processed! ---")

if __name__ == "__main__":
    main()

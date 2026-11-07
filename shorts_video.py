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

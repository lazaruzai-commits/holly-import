#!/usr/bin/env bash
# Re-encode the home-page hero videos for the web and extract a poster frame
# for each one.
#
#   static/video/<id>.mp4          original (1080p, 3–8 Mbps, up to 34 MB)
#   static/video/<id>-720p.mp4     web version (720p, ~1.5 Mbps, no audio)
#   static/video/posters/<id>.jpg  first-frame poster (1280px wide, ~50 KB)
#
# app.py prefers the -720p file and the poster when they exist, so this script
# is safe to run before or after deploying the code. Requires ffmpeg.
#
#   ./scripts/encode_hero_videos.sh            # all hero clips
#   ./scripts/encode_hero_videos.sh mg-5       # just one
#   POSTERS_ONLY=1 ./scripts/encode_hero_videos.sh   # re-extract posters only
#
# The originals are left untouched.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v ffmpeg >/dev/null || { echo "ffmpeg not found (Debian/Ubuntu: sudo apt install ffmpeg)"; exit 1; }

CLIPS=("$@")
[ ${#CLIPS[@]} -eq 0 ] && CLIPS=(mg-3 mg-rx9 mg-rx5 hero mg-5)

# Second at which each clip shows the car clearly (chosen by eye).
poster_time() {
  case "$1" in
    mg-3) echo 3 ;; mg-rx9) echo 3 ;; mg-rx5) echo 12 ;; hero) echo 8 ;; mg-5) echo 25 ;;
    *) echo 1 ;;
  esac
}

mkdir -p static/video/posters
for id in "${CLIPS[@]}"; do
  in="static/video/$id.mp4"
  out="static/video/$id-720p.mp4"
  poster="static/video/posters/$id.jpg"
  [ -f "$in" ] || { echo "skip $id: $in missing"; continue; }

  echo "== $id"
  if [ -z "${POSTERS_ONLY:-}" ]; then
    # 720p, H.264 high profile, capped at ~1.6 Mbps, no audio (slides are muted),
    # faststart so playback begins before the whole file arrives.
    ffmpeg -y -v error -stats -i "$in" \
      -vf "scale=-2:720" -c:v libx264 -preset slow -profile:v high -level 4.0 \
      -crf 26 -maxrate 1600k -bufsize 3200k -pix_fmt yuv420p \
      -movflags +faststart -an "$out"
  fi

  # Poster: a frame where the car is visible, 1280px wide, JPEG quality ~85.
  ffmpeg -y -v error -ss "$(poster_time "$id")" -i "$in" -frames:v 1 -vf "scale=1280:-2" -q:v 4 "$poster"

  printf "   %s -> %s  (%s)  poster %s\n" \
    "$(du -h "$in" | cut -f1)" "$(du -h "$out" | cut -f1)" "$out" "$(du -h "$poster" | cut -f1)"
done

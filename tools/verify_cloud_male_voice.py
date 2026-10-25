"""Verify deployed default speaker and a real public speech response."""
import json
from pathlib import Path
import time
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.voice_profile import STANDARD_TEXT, public_profile
EXPECTED = 'zh_male_taocheng_uranus_bigtts'
base = 'https://xiaoyin.onrender.com'
deadline = time.monotonic() + 150
while time.monotonic() < deadline:
    try:
        request = urllib.request.Request(base + '/api/health', headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=30) as response:
            health = json.load(response)
        voice = health.get('capabilities', {}).get('tts', {}).get('voice')
        profile = health.get('capabilities', {}).get('tts', {}).get('profile')
        if voice == EXPECTED and profile == public_profile():
            print('Public default male voice verified:', voice, flush=True)
            break
        print('Waiting for Render male-voice deployment', flush=True)
    except Exception as error:
        print('Deployment health not ready:', type(error).__name__, flush=True)
    time.sleep(10)
else:
    raise SystemExit('Deployment not verified before timeout')
body = json.dumps({'text': STANDARD_TEXT, 'voice': 'ignored-request-override'}, ensure_ascii=False).encode('utf-8')
request = urllib.request.Request(base + '/api/tts', data=body,
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(request, timeout=60) as response:
    audio = response.read()
    assert response.headers.get('Content-Type', '').startswith('audio/')
assert len(audio) > 1000
(ROOT / 'data/forest_male_voice_public.mp3').write_bytes(audio)
print('Public speech generation verified:', len(audio), 'audio bytes', flush=True)

import os
import time
import json
import urllib.request

# Load API key from .env file
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

load_env()

API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")
AUDIO_FILE = os.path.join(os.path.dirname(__file__), "tiktok-audio.mp3")
BASE_URL = "https://api.assemblyai.com"

if not API_KEY:
    print("ERROR: No API key found. Check your .env file.")
    exit(1)

if not os.path.exists(AUDIO_FILE):
    print("ERROR: tiktok-audio.mp3 not found. Run the yt-dlp download step first.")
    exit(1)

def api_request(method, path, data=None, binary=None):
    headers = {"Authorization": API_KEY}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    elif binary is not None:
        body = binary
        headers["Content-Type"] = "application/octet-stream"
    else:
        body = None
    req = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# Step 1: Upload the audio file
print("Step 1: Uploading audio to AssemblyAI...")
with open(AUDIO_FILE, "rb") as f:
    audio_data = f.read()
upload_result = api_request("POST", "/v2/upload", binary=audio_data)
upload_url = upload_result["upload_url"]
print(f"  Uploaded successfully.\n")

# Step 2: Request transcription using the new speech_models field
print("Step 2: Requesting transcription...")
transcript_result = api_request("POST", "/v2/transcript", data={
    "audio_url": upload_url,
    "speech_models": ["universal-2"]
})
transcript_id = transcript_result["id"]
print(f"  Job started (ID: {transcript_id})\n")

# Step 3: Poll until done
print("Step 3: Waiting for result (usually 15-30 seconds)...")
while True:
    poll = api_request("GET", f"/v2/transcript/{transcript_id}")
    status = poll["status"]
    print(f"  Status: {status}")
    if status == "completed":
        break
    elif status == "error":
        print(f"\nERROR: {poll.get('error')}")
        exit(1)
    time.sleep(3)

print("\n" + "=" * 60)
print("TRANSCRIPT (what the creator said in the video):")
print("=" * 60)
print(poll["text"])
print("=" * 60)
print(f"\nWord count: {len(poll['text'].split())} words")

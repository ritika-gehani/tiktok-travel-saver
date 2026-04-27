import json
import urllib.request

# TikTok URL
TIKTOK_URL = "https://www.tiktok.com/@nina.pemb/video/7497965157923032342"

# Fetch oEmbed data
oembed_url = f"https://www.tiktok.com/oembed?url={TIKTOK_URL}"

print("Fetching caption from TikTok oEmbed...")
with urllib.request.urlopen(oembed_url) as response:
    data = json.loads(response.read())

# Save to file
with open("caption-data.json", "w") as f:
    json.dump(data, f, indent=2)

print("\nCaption data saved to caption-data.json")
print("\nTitle/Caption:")
print("=" * 60)
print(data.get("title", ""))
print("=" * 60)
print(f"\nAuthor: {data.get('author_name', '')}")

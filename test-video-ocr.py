import os
import cv2
import pytesseract
import json

# Configuration
VIDEO_FILE = os.path.join(os.path.dirname(__file__), "tiktok-video.mp4")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "ocr-results.json")
SAMPLE_INTERVAL = 1  # Extract one frame per second

if not os.path.exists(VIDEO_FILE):
    print("ERROR: tiktok-video.mp4 not found. Run the yt-dlp download step first.")
    exit(1)

print("=" * 60)
print("TikTok Video OCR Test")
print("=" * 60)
print(f"Video file: {VIDEO_FILE}")
print(f"Sampling: 1 frame per {SAMPLE_INTERVAL} second(s)\n")

# Open the video file
video = cv2.VideoCapture(VIDEO_FILE)

# Get video properties
fps = video.get(cv2.CAP_PROP_FPS)  # Frames per second
total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
duration_seconds = total_frames / fps

print(f"Video info:")
print(f"  FPS: {fps:.2f}")
print(f"  Total frames: {total_frames}")
print(f"  Duration: {duration_seconds:.2f} seconds")
print(f"  Frames to sample: ~{int(duration_seconds / SAMPLE_INTERVAL)}\n")

print("Starting OCR extraction...\n")

results = []
frame_count = 0
frames_to_skip = int(fps * SAMPLE_INTERVAL)  # How many frames = 1 second

while True:
    # Read the next frame
    success, frame = video.read()
    
    if not success:
        break  # End of video
    
    # Only process every Nth frame (where N = frames per second)
    if frame_count % frames_to_skip == 0:
        timestamp_seconds = frame_count / fps
        
        # Convert frame to grayscale (improves OCR accuracy)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Run OCR on the frame
        text = pytesseract.image_to_string(gray_frame)
        
        # Clean up the text (remove extra whitespace)
        text = text.strip()
        
        if text:  # Only record if text was found
            result = {
                "timestamp_seconds": round(timestamp_seconds, 2),
                "text": text
            }
            results.append(result)
            print(f"[{timestamp_seconds:.2f}s] Found text:")
            print(f"  {text[:100]}{'...' if len(text) > 100 else ''}")  # Print first 100 chars
            print()
    
    frame_count += 1

video.release()

print("=" * 60)
print(f"OCR extraction complete!")
print(f"Total frames processed: {len(results)}")
print(f"Saving results to: {OUTPUT_FILE}\n")

# Save results to JSON file
with open(OUTPUT_FILE, "w") as f:
    json.dump(results, f, indent=2)

print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Frames with text detected: {len(results)}")

if results:
    print("\nSample results:")
    for i, result in enumerate(results[:5]):  # Show first 5
        print(f"\n[{result['timestamp_seconds']}s]")
        print(f"  {result['text'][:80]}{'...' if len(result['text']) > 80 else ''}")
    
    if len(results) > 5:
        print(f"\n... and {len(results) - 5} more frames")
    
    print(f"\nFull results saved to: {OUTPUT_FILE}")
else:
    print("\nNo text was detected in any frame.")
    print("This could mean:")
    print("  - The video has no on-screen text")
    print("  - The text is too stylized for Tesseract to read")
    print("  - The video quality is too low")

print("=" * 60)

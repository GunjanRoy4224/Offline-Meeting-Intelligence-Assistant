"""
Download AMI Meeting Corpus - real meeting recordings and transcripts.
Pulls directly from the official open-source mirrors to avoid auth walls.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict
import requests

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

AMI_OFFICIAL_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/"
SAMPLE_MEETINGS_DIR = Path(__file__).parent / "sample_meetings"

# Grabbing the headset mix wav files directly from the university servers
SAMPLE_MEETINGS = [
    {
        "id": "ES2002a",
        "audio_url": f"{AMI_OFFICIAL_URL}ES2002a/audio/ES2002a.Mix-Headset.wav",
        "duration": "30 min",
        "speakers": 4,
    },
    {
        "id": "ES2005a",
        "audio_url": f"{AMI_OFFICIAL_URL}ES2005a/audio/ES2005a.Mix-Headset.wav",
        "duration": "30 min",
        "speakers": 4,
    },
    {
        "id": "IS1000a",
        "audio_url": f"{AMI_OFFICIAL_URL}IS1000a/audio/IS1000a.Mix-Headset.wav",
        "duration": "30 min",
        "speakers": 2,
    },
]

# ============================================================================
# DOWNLOADER FUNCTIONS
# ============================================================================

def download_file(url: str, output_path: Path, timeout: int = 300) -> bool:
    """Download file from URL with a simple progress tracker."""
    try:
        logger.info(f"Downloading: {url}")
        
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Print progress on the same line
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r  {percent:.1f}% ({downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB)", end="")
        
        print() # New line after progress finishes
        logger.info(f"✓ Downloaded: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"✗ Download failed: {e}")
        return False


def download_sample_meetings(num_samples: int = 3) -> List[Dict]:
    """Download real meeting audio from AMI corpus."""
    SAMPLE_MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
    
    downloaded = []
    samples = SAMPLE_MEETINGS[:min(num_samples, len(SAMPLE_MEETINGS))]
    
    for meeting in samples:
        meeting_id = meeting['id']
        
        # Download audio
        audio_file = SAMPLE_MEETINGS_DIR / f"{meeting_id}_audio.wav"
        if not audio_file.exists():
            logger.info(f"\nDownloading audio for {meeting_id}...")
            if download_file(meeting['audio_url'], audio_file):
                downloaded.append({
                    "id": meeting_id,
                    "audio": str(audio_file)
                })
            else:
                logger.warning(f"Skipping {meeting_id} - audio download failed")
                continue
        else:
            logger.info(f"Audio already exists: {audio_file}")
            downloaded.append({
                "id": meeting_id,
                "audio": str(audio_file)
            })
            
    return downloaded


def create_sample_synthetic_meeting() -> tuple[str, str]:
    """Create a 2-second synthetic audio file just to check if the pipeline connects."""
    try:
        import wave
        
        logger.info("Creating synthetic test meeting...")
        SAMPLE_MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
        
        audio_file = SAMPLE_MEETINGS_DIR / "test_synthetic_audio.wav"
        sample_rate = 16000
        duration = 2 
        
        with wave.open(str(audio_file), 'w') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            silence = b'\x00\x00' * (sample_rate * duration)
            wav_file.writeframes(silence)
            
        logger.info(f"✓ Created synthetic meeting: {audio_file}")
        return str(audio_file), "test"
    
    except Exception as e:
        logger.error(f"Error creating synthetic meeting: {e}")
        return None, None


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1 and sys.argv[1] == "synthetic":
        audio_file, _ = create_sample_synthetic_meeting()
        if audio_file:
            print(f"\n✓ Synthetic meeting created at: {audio_file}")
            
    else:
        num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        print(f"\nDownloading {num} sample meeting(s)...")
        print("(These files are usually big, let it run)\n")
        
        downloaded = download_sample_meetings(num_samples=num)
        
        if downloaded:
            print(f"\n✓ Done. Grabbed {len(downloaded)} meeting(s):")
            for m in downloaded:
                print(f"  - {m['id']}: {m['audio']}")
        else:
            print("\n✗ Didn't get anything. Try checking your internet or run `synthetic` instead.")
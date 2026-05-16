"""
Process raw audio and transcript data into usable format.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import re

logger = logging.getLogger(__name__)

# ============================================================================
# AUDIO PROCESSING
# ============================================================================

def validate_audio_file(file_path: str) -> bool:
    """Check if file is valid audio."""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return False
    
    valid_formats = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}
    if path.suffix.lower() not in valid_formats:
        logger.error(f"Invalid audio format: {path.suffix}")
        return False
    
    return True


def get_audio_info(file_path: str) -> Optional[Dict]:
    """Get audio file info (duration, format, size)."""
    try:
        import librosa
        
        path = Path(file_path)
        if not path.exists():
            return None
        
        y, sr = librosa.load(file_path, sr=None)
        duration_seconds = len(y) / sr
        
        return {
            "file": str(path),
            "filename": path.name,
            "format": path.suffix.lower(),
            "size_mb": path.stat().st_size / (1024*1024),
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_seconds / 60,
            "sample_rate": sr,
            "mono": len(y.shape) == 1
        }
    except ImportError:
        logger.warning("librosa not installed. Install with: pip install librosa")
        return None
    except Exception as e:
        logger.error(f"Error getting audio info: {e}")
        return None


def convert_audio_format(input_file: str, output_file: str, target_format: str = "wav") -> bool:
    """Convert audio to different format (requires ffmpeg)."""
    try:
        import librosa
        import soundfile as sf
        
        logger.info(f"Converting {input_file} to {target_format}...")
        
        y, sr = librosa.load(input_file, sr=None)
        sf.write(output_file, y, sr)
        
        logger.info(f"✓ Converted: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        return False


def resample_audio(input_file: str, output_file: str, target_sr: int = 16000) -> bool:
    """Resample audio to target sample rate (required for Whisper)."""
    try:
        import librosa
        import soundfile as sf
        
        logger.info(f"Resampling {input_file} to {target_sr}Hz...")
        
        y, sr = librosa.load(input_file, sr=None)
        y_resampled = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        
        sf.write(output_file, y_resampled, target_sr)
        
        logger.info(f"✓ Resampled: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Resample failed: {e}")
        return False

# ============================================================================
# TRANSCRIPT PROCESSING
# ============================================================================

def clean_transcript(text: str) -> str:
    """Clean transcript text."""
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove timestamp patterns [HH:MM:SS]
    text = re.sub(r'\[\d{1,2}:\d{2}:\d{2}\]', '', text)
    
    # Remove speaker tags [Speaker X:]
    text = re.sub(r'\[Speaker \w+:\]', '', text)
    
    # Remove noise markers <NOISE>, <SIGH>, etc.
    text = re.sub(r'<[A-Z_]+>', '', text)
    
    # Fix multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def parse_ami_transcript(file_path: str) -> str:
    """Parse AMI corpus transcript format."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        transcript_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove timing info [0] [1000] etc
            line = re.sub(r'\[\d+\]', '', line)
            
            # Keep speaker labels for context
            if ':' in line:
                transcript_text.append(line)
            else:
                transcript_text.append(line)
        
        full_text = ' '.join(transcript_text)
        return clean_transcript(full_text)
    
    except Exception as e:
        logger.error(f"Error parsing transcript: {e}")
        return ""


def validate_transcript(text: str, min_length: int = 100) -> bool:
    """Validate transcript has reasonable content."""
    if not text or len(text) < min_length:
        logger.error(f"Transcript too short: {len(text)} chars")
        return False
    
    # Check it's not just garbage
    words = text.split()
    if len(words) < 20:
        logger.error(f"Transcript too few words: {len(words)}")
        return False
    
    return True

# ============================================================================
# MEETING PROCESSING
# ============================================================================

def process_meeting(
    audio_file: str,
    transcript_file: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Dict:
    """
    Process a complete meeting (audio + transcript).
    
    Returns: {
        "meeting_id": "ES2002a",
        "audio": {
            "file": "...",
            "duration_minutes": 30,
            "size_mb": 150,
            ...
        },
        "transcript": {
            "file": "...",
            "text": "full transcript...",
            "word_count": 5000,
            "char_count": 25000
        },
        "ready_for_processing": True
    }
    """
    logger.info(f"Processing meeting from {audio_file}")
    
    meeting_id = Path(audio_file).stem.replace('_audio', '')
    
    result = {
        "meeting_id": meeting_id,
        "audio": None,
        "transcript": None,
        "ready_for_processing": False
    }
    
    # Process audio
    if validate_audio_file(audio_file):
        audio_info = get_audio_info(audio_file)
        if audio_info:
            result["audio"] = audio_info
            logger.info(f"✓ Audio: {audio_info['duration_minutes']:.1f} min, {audio_info['size_mb']:.1f}MB")
    
    # Process transcript
    if transcript_file:
        if Path(transcript_file).exists():
            transcript_text = parse_ami_transcript(transcript_file)
            
            if validate_transcript(transcript_text):
                result["transcript"] = {
                    "file": str(transcript_file),
                    "text": transcript_text,
                    "word_count": len(transcript_text.split()),
                    "char_count": len(transcript_text)
                }
                logger.info(f"✓ Transcript: {len(transcript_text.split())} words")
        else:
            logger.warning(f"Transcript not found: {transcript_file}")
    
    # Check ready
    result["ready_for_processing"] = result["audio"] is not None
    
    return result


def batch_process_meetings(meetings_dir: str) -> List[Dict]:
    """Process all meetings in a directory."""
    meetings = []
    
    dir_path = Path(meetings_dir)
    if not dir_path.exists():
        logger.error(f"Directory not found: {meetings_dir}")
        return meetings
    
    audio_files = list(dir_path.glob("*_audio.*"))
    
    logger.info(f"Found {len(audio_files)} audio files")
    
    for audio_file in audio_files:
        meeting_id = audio_file.stem.replace('_audio', '')
        transcript_file = dir_path / f"{meeting_id}_transcript.txt"
        
        result = process_meeting(
            str(audio_file),
            str(transcript_file) if transcript_file.exists() else None
        )
        
        meetings.append(result)
    
    logger.info(f"Processed {len(meetings)} meetings")
    
    return meetings


# ============================================================================
# DATA EXPORT
# ============================================================================

def save_meeting_metadata(meeting: Dict, output_file: str) -> bool:
    """Save meeting metadata to JSON."""
    try:
        with open(output_file, 'w') as f:
            json.dump(meeting, f, indent=2)
        logger.info(f"✓ Saved metadata: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving metadata: {e}")
        return False


def save_transcript(meeting: Dict, output_file: str) -> bool:
    """Save cleaned transcript to file."""
    try:
        if not meeting.get("transcript"):
            logger.warning("No transcript in meeting data")
            return False
        
        text = meeting["transcript"]["text"]
        with open(output_file, 'w') as f:
            f.write(text)
        
        logger.info(f"✓ Saved transcript: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving transcript: {e}")
        return False


def export_meetings_manifest(meetings: List[Dict], output_file: str) -> bool:
    """Export manifest of all processed meetings."""
    try:
        manifest = {
            "total_meetings": len(meetings),
            "meetings": []
        }
        
        total_duration = 0
        total_size = 0
        
        for meeting in meetings:
            if meeting["ready_for_processing"]:
                audio = meeting.get("audio", {})
                transcript = meeting.get("transcript", {})
                
                manifest["meetings"].append({
                    "meeting_id": meeting["meeting_id"],
                    "audio_file": audio.get("filename"),
                    "duration_minutes": audio.get("duration_minutes"),
                    "size_mb": audio.get("size_mb"),
                    "transcript_words": transcript.get("word_count"),
                    "ready": meeting["ready_for_processing"]
                })
                
                total_duration += audio.get("duration_minutes", 0)
                total_size += audio.get("size_mb", 0)
        
        manifest["total_duration_minutes"] = total_duration
        manifest["total_size_mb"] = total_size
        
        with open(output_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"✓ Saved manifest: {output_file}")
        logger.info(f"  Total: {len(manifest['meetings'])} meetings, {total_duration:.1f}min, {total_size:.1f}MB")
        
        return True
    except Exception as e:
        logger.error(f"Error exporting manifest: {e}")
        return False

# ============================================================================
# STATISTICS
# ============================================================================

def get_meeting_stats(meeting: Dict) -> Dict:
    """Get statistics about a meeting."""
    stats = {
        "meeting_id": meeting["meeting_id"],
        "audio_duration_minutes": 0,
        "audio_size_mb": 0,
        "transcript_words": 0,
        "transcript_chars": 0,
        "words_per_minute": 0
    }
    
    if meeting.get("audio"):
        audio = meeting["audio"]
        stats["audio_duration_minutes"] = audio.get("duration_minutes", 0)
        stats["audio_size_mb"] = audio.get("size_mb", 0)
    
    if meeting.get("transcript"):
        transcript = meeting["transcript"]
        stats["transcript_words"] = transcript.get("word_count", 0)
        stats["transcript_chars"] = transcript.get("char_count", 0)
        
        if stats["audio_duration_minutes"] > 0:
            stats["words_per_minute"] = stats["transcript_words"] / stats["audio_duration_minutes"]
    
    return stats


def print_meeting_stats(meetings: List[Dict]) -> None:
    """Print statistics for all meetings."""
    if not meetings:
        print("No meetings to analyze")
        return
    
    print("\n" + "="*60)
    print("MEETING STATISTICS")
    print("="*60)
    
    all_stats = []
    for meeting in meetings:
        if meeting["ready_for_processing"]:
            stats = get_meeting_stats(meeting)
            all_stats.append(stats)
            
            print(f"\n{stats['meeting_id']}")
            print(f"  Duration: {stats['audio_duration_minutes']:.1f} min")
            print(f"  Size: {stats['audio_size_mb']:.1f} MB")
            print(f"  Words: {stats['transcript_words']:,}")
            print(f"  WPM: {stats['words_per_minute']:.0f}")
    
    if all_stats:
        avg_duration = sum(s['audio_duration_minutes'] for s in all_stats) / len(all_stats)
        total_words = sum(s['transcript_words'] for s in all_stats)
        total_size = sum(s['audio_size_mb'] for s in all_stats)
        
        print(f"\n{'TOTALS':}")
        print(f"  Meetings: {len(all_stats)}")
        print(f"  Avg Duration: {avg_duration:.1f} min")
        print(f"  Total Words: {total_words:,}")
        print(f"  Total Size: {total_size:.1f} MB")
    
    print("="*60 + "\n")

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python data/processor.py <audio_file> [transcript_file]")
        print("  python data/processor.py --batch <meetings_dir>")
        sys.exit(1)
    
    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("Usage: python data/processor.py --batch <meetings_dir>")
            sys.exit(1)
        
        meetings = batch_process_meetings(sys.argv[2])
        print_meeting_stats(meetings)
        
        export_meetings_manifest(
            meetings,
            "data/processed/manifest.json"
        )
    
    else:
        audio_file = sys.argv[1]
        transcript_file = sys.argv[2] if len(sys.argv) > 2 else None
        
        result = process_meeting(audio_file, transcript_file)
        
        print(json.dumps(result, indent=2))
        print_meeting_stats([result])

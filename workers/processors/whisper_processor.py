"""
Faster-Whisper speech-to-text processor.

Converts audio files to text using OpenAI's Whisper model.
Optimized for speed with int8 quantization on CPU.
"""

import logging
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from app.config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
)

logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL MODEL INSTANCE (loaded once per worker)
# ============================================================================

_model_instance = None


def get_whisper_model() -> WhisperModel:
    """
    Get or initialize the Whisper model.
    
    The model is loaded once and reused for all transcriptions.
    This is efficient because the model is large (~1.5GB) and takes
    time to load. By loading it once per worker, we avoid repeated
    initialization overhead.
    
    Returns:
        WhisperModel: Loaded Whisper model instance
    """
    global _model_instance
    
    if _model_instance is None:
        logger.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}")
        logger.info(f"  Device: {WHISPER_DEVICE}")
        logger.info(f"  Compute type: {WHISPER_COMPUTE_TYPE}")
        
        try:
            _model_instance = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
            logger.info("✓ Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    return _model_instance


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio file to text using Faster-Whisper.
    
    This function:
    1. Loads the audio file
    2. Runs it through Whisper
    3. Returns the full transcript as a single string
    
    Faster-Whisper is faster than the original Whisper because:
    - It uses CTransformers (optimized inference)
    - It supports int8 quantization (smaller, faster)
    - It batches segments for efficiency
    
    Benchmark (Raspberry Pi 4, 15-minute audio):
    - Original Whisper: ~45 minutes
    - Faster-Whisper (int8): ~8 minutes
    
    Args:
        file_path: Path to audio file (MP3, WAV, OGG, FLAC, M4A, etc.)
    
    Returns:
        str: Complete transcript from the audio file
    
    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If transcription fails
    """
    
    file_path = Path(file_path)
    
    # Validate file exists
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    logger.info(f"Transcribing audio: {file_path}")
    logger.info(f"  File size: {file_path.stat().st_size / (1024*1024):.1f} MB")
    
    try:
        # Get model instance
        model = get_whisper_model()
        
        # Transcribe
        segments, info = model.transcribe(
            str(file_path),
            language=WHISPER_LANGUAGE,
            beam_size=1,       # Greedy decoding — 3-5x faster on CPU than beam_size=5
            best_of=1,         # No sampling competition needed on CPU
            vad_filter=True,   # Skip silence padding — significant speedup
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        
        logger.info(f"Transcription details:")
        logger.info(f"  Duration: {info.duration:.1f} seconds")
        logger.info(f"  Language: {info.language}")
        logger.info(f"  Language probability: {info.language_probability:.2%}")
        
        # Combine all segments into single transcript
        transcript_parts = []
        segment_count = 0
        
        for segment in segments:
            transcript_parts.append(segment.text)
            segment_count += 1
            
            # Log every segment so the worker never appears hung
            logger.info(f"  [seg {segment_count}] {segment.start:.1f}s \u2192 {segment.end:.1f}s | {segment.text[:60].strip()}")
        
        transcript = " ".join(transcript_parts)
        
        logger.info(f"Transcription complete:")
        logger.info(f"  Segments: {segment_count}")
        logger.info(f"  Total length: {len(transcript)} characters")
        
        return transcript
    
    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}", exc_info=True)
        raise ValueError(f"Could not transcribe audio: {str(e)}")


# ============================================================================
# OPTIONAL: BATCH TRANSCRIPTION
# ============================================================================

def transcribe_multiple_files(file_paths: list) -> dict:
    """
    Transcribe multiple audio files.
    
    Useful if you want to process multiple files sequentially.
    For parallel processing across files, use separate Celery tasks.
    
    Args:
        file_paths: List of paths to audio files
    
    Returns:
        dict: Mapping of file path to transcript
    
    Example:
        results = transcribe_multiple_files([
            "meeting1.mp3",
            "meeting2.wav",
            "meeting3.m4a"
        ])
        print(results["meeting1.mp3"])  # Full transcript
    """
    results = {}
    
    for file_path in file_paths:
        try:
            logger.info(f"Transcribing: {file_path}")
            transcript = transcribe_audio(file_path)
            results[file_path] = {"status": "success", "transcript": transcript}
        except Exception as e:
            logger.error(f"Failed to transcribe {file_path}: {e}")
            results[file_path] = {"status": "failed", "error": str(e)}
    
    return results


# ============================================================================
# OPTIONAL: CHUNK-BASED TRANSCRIPTION (FOR VERY LONG AUDIO)
# ============================================================================

def transcribe_audio_chunked(file_path: str, chunk_duration: int = 300) -> str:
    """
    Transcribe audio in chunks (for very long files).
    
    If you have a 2-hour meeting, Whisper might struggle.
    This splits it into 5-minute chunks, transcribes each,
    then combines the results.
    
    Args:
        file_path: Path to audio file
        chunk_duration: Seconds per chunk (default 300 = 5 minutes)
    
    Returns:
        str: Complete transcript
    
    Note:
        This is more complex and usually not needed for <1 hour audio.
        Faster-Whisper handles long audio well with streaming.
    """
    import librosa
    import soundfile as sf
    import tempfile
    
    logger.info(f"Chunked transcription: {file_path} ({chunk_duration}s chunks)")
    
    # Load audio
    audio, sr = librosa.load(file_path, sr=16000)
    duration = len(audio) / sr
    
    logger.info(f"Audio duration: {duration:.1f} seconds")
    
    # Calculate chunks
    chunk_size = chunk_duration * sr
    num_chunks = int(duration / chunk_duration) + 1
    
    logger.info(f"Will process {num_chunks} chunks")
    
    transcripts = []
    
    for i in range(num_chunks):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        
        chunk_audio = audio[start_idx:end_idx]
        
        # Save chunk to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, chunk_audio, sr)
            
            # Transcribe chunk
            try:
                transcript = transcribe_audio(tmp.name)
                transcripts.append(transcript)
                logger.info(f"  Chunk {i+1}/{num_chunks} done")
            finally:
                Path(tmp.name).unlink()
    
    return " ".join(transcripts)

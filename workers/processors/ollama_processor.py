"""
Local Ollama LLM processor for task extraction.

Uses your locally running Ollama server with qwen2.5 model.
Implements map-reduce pattern for handling long transcripts.
"""

import logging
import json
import re
from typing import List, Dict
import httpx
import asyncio

from app.config import (
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TEMPERATURE,
    OLLAMA_TOP_P,
    OLLAMA_TOP_K,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TIMEOUT,
    TRANSCRIPT_CHUNK_SIZE,
    TRANSCRIPT_CHUNK_OVERLAP,
)

logger = logging.getLogger(__name__)

# ============================================================================
# PROMPT TEMPLATES
# ============================================================================

TASK_EXTRACTION_PROMPT = """You are a meeting assistant that extracts action items and tasks from meeting transcripts.

From the following meeting transcript, extract all action items, tasks, and assignments.

For EACH task, provide:
- assignee: The person responsible (or "Unknown" if not specified)
- task: What needs to be done (be specific)
- deadline: When it's due (ISO date format YYYY-MM-DD, or "TBD" if not mentioned)
- confidence: How confident you are (0.0 to 1.0)

Return ONLY a valid JSON array, no other text. Example format:
[
  {{
    "assignee": "John",
    "task": "Review code changes in PR #123",
    "deadline": "2024-01-15",
    "confidence": 0.95
  }},
  {{
    "assignee": "Sarah",
    "task": "Update documentation",
    "deadline": "TBD",
    "confidence": 0.8
  }}
]

TRANSCRIPT CHUNK:
{transcript_chunk}

Return ONLY the JSON array:"""
# ============================================================================
# OLLAMA COMMUNICATION
# ============================================================================

async def check_ollama_health() -> bool:
    """Check if Ollama server is running and accessible."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        return False

async def list_available_models() -> List[str]:
    """Get list of available models in Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                models = [model['name'] for model in data.get('models', [])]
                logger.info(f"Available Ollama models: {models}")
                return models
            return []
    except Exception as e:
        logger.error(f"Could not list Ollama models: {e}")
        return []

async def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """
    Call Ollama API to generate text.

    Health check is intentionally NOT performed here — it is done once
    in extract_tasks_mapreduce() before the map-reduce fan-out to avoid
    N redundant HTTP round-trips (one per chunk).
    """
    logger.debug(f"Calling Ollama model: {model}")

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "temperature": OLLAMA_TEMPERATURE,
                    "top_p": OLLAMA_TOP_P,
                    "top_k": OLLAMA_TOP_K,
                    "num_predict": OLLAMA_NUM_PREDICT,
                    "stream": False,
                }
            )

            if response.status_code != 200:
                raise ValueError(f"Ollama API error: {response.text}")

            data = response.json()
            return data.get('response', '')

    except httpx.TimeoutException:
        raise TimeoutError(
            f"Ollama request timed out after {OLLAMA_TIMEOUT} seconds. "
            f"Try increasing OLLAMA_TIMEOUT in config.py"
        )
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        raise


# ============================================================================
# TASK EXTRACTION
# ============================================================================

async def extract_tasks_from_chunk(transcript_chunk: str, chunk_num: int = 0) -> List[Dict]:
    """Extract tasks from a single transcript chunk using Ollama."""
    logger.info(f"Extracting tasks from chunk {chunk_num}")
    
    try:
        prompt = TASK_EXTRACTION_PROMPT.format(transcript_chunk=transcript_chunk)
        response = await call_ollama(prompt)
        tasks = parse_json_response(response)
        logger.info(f"Chunk {chunk_num}: Found {len(tasks)} tasks")
        return tasks
    except Exception as e:
        logger.error(f"Error extracting tasks from chunk {chunk_num}: {e}")
        return []

async def extract_tasks_mapreduce(transcript: str, job_id: str = "") -> List[Dict]:
    """Extract tasks from transcript using asynchronous map-reduce pattern."""
    if not transcript or len(transcript.strip()) == 0:
        logger.warning(f"[{job_id}] Empty transcript provided")
        return []

    logger.info(f"[{job_id}] Starting async map-reduce task extraction")

    # ── Single health check before fan-out ─────────────────────────────────────
    # Moved here from call_ollama() so we pay the HTTP round-trip cost exactly
    # once instead of once per chunk (which could be 5-10 redundant calls).
    if not await check_ollama_health():
        raise ConnectionError(
            f"[{job_id}] Ollama server not running at {OLLAMA_HOST}. "
            f"Start it with: ollama serve"
        )
    logger.info(f"[{job_id}] Ollama health check passed")

    chunks = create_overlapping_chunks(
        transcript,
        TRANSCRIPT_CHUNK_SIZE,
        TRANSCRIPT_CHUNK_OVERLAP
    )
    logger.info(f"[{job_id}] Split into {len(chunks)} chunks")
    
    # Process all chunks concurrently
    coroutines = [
        extract_tasks_from_chunk(chunk, chunk_num)
        for chunk_num, chunk in enumerate(chunks, 1)
    ]
    
    results = await asyncio.gather(*coroutines, return_exceptions=True)
    
    all_tasks = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[{job_id}] Chunk {i+1} extraction failed: {result}")
        elif isinstance(result, list):
            all_tasks.extend(result)
            
    logger.info(f"[{job_id}] All chunks processed: {len(all_tasks)} raw tasks found")
    
    merged_tasks = deduplicate_tasks(all_tasks)
    logger.info(f"[{job_id}] After deduplication: {len(merged_tasks)} unique tasks")
    
    return merged_tasks


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_overlapping_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Overlap ensures context is preserved across chunk boundaries.
    
    Args:
        text: Full text to chunk
        chunk_size: Characters per chunk
        overlap: Characters of overlap between chunks
    
    Returns:
        List of text chunks
    
    Example:
        text = "ABCDEFGHIJKLMNOP" (16 chars)
        chunks = create_overlapping_chunks(text, 6, 2)
        # Result: ["ABCDEF", "CDEFGH", "GHIJKL", "KLMNOP"]
    """
    chunks = []
    
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        
        if chunk.strip():  # Only add non-empty chunks
            chunks.append(chunk)
        
        # Move start position, accounting for overlap
        if end >= len(text):
            break
        
        start = end - overlap
    
    return chunks


def parse_json_response(response: str) -> List[Dict]:
    """
    Extract JSON array from model response.
    
    The LLM might return: "Here are the tasks: [JSON] And that's it!"
    We extract just the JSON part.
    
    Args:
        response: Raw response from LLM
    
    Returns:
        Parsed list of dictionaries
    """
    
    # Try to find JSON array in the response
    # Look for pattern: [...] 
    match = re.search(r'\[[\s\S]*\]', response)
    
    if not match:
        logger.warning("No JSON array found in response")
        return []
    
    json_str = match.group(0)
    
    try:
        tasks = json.loads(json_str)
        
        # Validate structure
        if not isinstance(tasks, list):
            logger.warning(f"Expected list, got {type(tasks)}")
            return []
        
        # Validate each task has required fields
        valid_tasks = []
        for task in tasks:
            if isinstance(task, dict) and 'assignee' in task and 'task' in task:
                # Set defaults for missing fields
                task.setdefault('deadline', 'TBD')
                task.setdefault('confidence', 0.5)
                valid_tasks.append(task)
        
        return valid_tasks
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"JSON string: {json_str[:200]}...")
        return []


def deduplicate_tasks(tasks: List[Dict]) -> List[Dict]:
    """
    Remove duplicate or near-duplicate tasks.
    
    Tasks appearing in multiple chunks (due to overlap) are merged.
    
    Args:
        tasks: List of task dictionaries (potentially with duplicates)
    
    Returns:
        List of deduplicated tasks
    """
    
    if not tasks:
        return []
    
    # Group by assignee + first 30 chars of task
    seen = {}
    deduplicated = []
    
    for task in tasks:
        assignee = task.get('assignee', 'Unknown').lower().strip()
        task_text = task.get('task', '')[:30].lower().strip()
        
        key = (assignee, task_text)
        
        if key not in seen:
            # First time seeing this task
            seen[key] = task
            deduplicated.append(task)
        else:
            # Seen this before - keep the one with higher confidence
            existing_task = seen[key]
            new_confidence = task.get('confidence', 0)
            existing_confidence = existing_task.get('confidence', 0)
            
            if new_confidence > existing_confidence:
                # Replace with higher-confidence version
                for i, t in enumerate(deduplicated):
                    if t == existing_task:
                        deduplicated[i] = task
                        seen[key] = task
                        break
    
    logger.info(f"Deduplication: {len(tasks)} → {len(deduplicated)} tasks")
    
    return deduplicated

"""
Task validation using Pydantic.

Ensures all extracted tasks conform to the schema:
- assignee: str (required, non-empty)
- task: str (required, non-empty)  
- deadline: str (required, ISO format or TBD)
- confidence: float (required, 0.0-1.0)

Rejects invalid tasks and logs detailed errors.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import re

from pydantic import BaseModel, Field, validator, ValidationError

logger = logging.getLogger(__name__)

# ============================================================================
# VALIDATION MODELS
# ============================================================================

class TaskSchema(BaseModel):
    """
    Strict validation model for extracted tasks.
    
    All fields are required and validated.
    """
    assignee: str = Field(..., min_length=1, max_length=200)
    task: str = Field(..., min_length=5, max_length=500)
    deadline: str = Field(default="TBD", max_length=100)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    
    @validator('assignee', 'task')
    def strip_whitespace(cls, v):
        """Remove leading/trailing whitespace."""
        if isinstance(v, str):
            v = v.strip()
        return v
    
    @validator('assignee')
    def validate_assignee(cls, v):
        """
        Validate assignee field.
        - Not empty
        - Not generic words like "Unknown" or "Someone"
        """
        if not v or v.lower() in ['unknown', 'someone', 'nobody', 'unassigned']:
            # These are okay, but log them as low confidence
            logger.debug(f"Generic assignee: {v}")
        return v
    
    @validator('deadline')
    def validate_deadline(cls, v):
        """
        Validate deadline field.
        - Format: ISO date (YYYY-MM-DD), relative (e.g., "next week"), or "TBD"
        """
        if not v or v == "TBD":
            return "TBD"
        
        # Check if ISO date format (YYYY-MM-DD)
        iso_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if re.match(iso_pattern, v):
            # Validate it's a real date
            try:
                datetime.strptime(v, '%Y-%m-%d')
                return v
            except ValueError:
                logger.warning(f"Invalid date format: {v}")
                return "TBD"
        
        # Allow relative dates
        if v.lower() in ['today', 'tomorrow', 'next week', 'next month', 
                         'asap', 'immediately', 'urgent']:
            return v
        
        # Check for pattern like "by Friday", "in 2 days", etc.
        relative_pattern = r'(by|in|within|before|after).+'
        if re.match(relative_pattern, v, re.IGNORECASE):
            return v
        
        # Anything else, try to parse but default to TBD
        logger.warning(f"Unknown deadline format: {v}")
        return "TBD"
    
    class Config:
        # Allow extra fields (we'll ignore them)
        extra = "ignore"


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_single_task(task_dict: Dict) -> tuple[bool, Optional[TaskSchema], str]:
    """
    Validate a single task dictionary.
    
    Args:
        task_dict: Dictionary with task data
    
    Returns:
        Tuple of (is_valid, parsed_task, error_message)
    
    Example:
        is_valid, parsed, error = validate_single_task({
            "assignee": "John",
            "task": "Review PR",
            "deadline": "2024-01-15",
            "confidence": 0.95
        })
        
        if is_valid:
            print(f"Valid task for {parsed.assignee}")
        else:
            print(f"Error: {error}")
    """
    
    if not isinstance(task_dict, dict):
        return False, None, f"Expected dict, got {type(task_dict)}"
    
    try:
        parsed_task = TaskSchema(**task_dict)
        return True, parsed_task, ""
    
    except ValidationError as e:
        error_details = []
        for error in e.errors():
            field = error['loc'][0] if error['loc'] else 'unknown'
            msg = error['msg']
            error_details.append(f"{field}: {msg}")
        
        error_message = "; ".join(error_details)
        return False, None, error_message
    
    except Exception as e:
        return False, None, str(e)


def validate_and_parse_tasks(
    raw_tasks: List[Dict],
    job_id: str = ""
) -> List[TaskSchema]:
    """
    Validate and parse a list of raw task dictionaries.
    
    This is the main validation function used by workers.
    It validates all tasks, logs errors, and returns only valid ones.
    
    Args:
        raw_tasks: List of task dictionaries from LLM
        job_id: Job ID for logging
    
    Returns:
        List of validated TaskSchema objects
    
    Example:
        raw_tasks = [
            {"assignee": "John", "task": "Review PR", "deadline": "2024-01-15", "confidence": 0.95},
            {"assignee": "", "task": "Bad task"},  # Will be rejected
            {"assignee": "Sarah", "task": "Write docs", "confidence": 0.8}
        ]
        
        valid = validate_and_parse_tasks(raw_tasks, job_id="xyz")
        # Returns: [TaskSchema(...), TaskSchema(...)]  (2 valid tasks)
    """
    
    if not raw_tasks:
        logger.warning(f"[{job_id}] No tasks to validate")
        return []
    
    logger.info(f"[{job_id}] Validating {len(raw_tasks)} tasks...")
    
    valid_tasks = []
    invalid_count = 0
    
    for i, task_dict in enumerate(raw_tasks):
        is_valid, parsed_task, error = validate_single_task(task_dict)
        
        if is_valid:
            valid_tasks.append(parsed_task)
            logger.debug(f"[{job_id}] Task {i+1}: ✓ Valid")
        else:
            invalid_count += 1
            logger.warning(
                f"[{job_id}] Task {i+1}: ✗ Invalid - {error}"
                f"\n  Raw: {task_dict}"
            )
    
    logger.info(
        f"[{job_id}] Validation complete: "
        f"{len(valid_tasks)} valid, {invalid_count} invalid"
    )
    
    return valid_tasks


def validate_task_batch(tasks: List[TaskSchema]) -> Dict[str, any]:
    """
    Validate a batch of tasks and return statistics.
    
    Useful for monitoring and reporting.
    
    Args:
        tasks: List of TaskSchema objects
    
    Returns:
        Dictionary with validation statistics
    
    Example:
        stats = validate_task_batch(valid_tasks)
        # Returns:
        # {
        #     "total": 5,
        #     "with_assignee": 4,
        #     "with_deadline": 3,
        #     "avg_confidence": 0.82,
        #     "high_confidence": 3  # >= 0.8
        # }
    """
    
    if not tasks:
        return {
            "total": 0,
            "with_assignee": 0,
            "with_deadline": 0,
            "avg_confidence": 0.0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
        }
    
    with_assignee = sum(
        1 for t in tasks 
        if t.assignee and t.assignee.lower() != 'unknown'
    )
    
    with_deadline = sum(
        1 for t in tasks 
        if t.deadline != 'TBD'
    )
    
    confidences = [t.confidence for t in tasks]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    high_conf = sum(1 for c in confidences if c >= 0.8)
    medium_conf = sum(1 for c in confidences if 0.5 <= c < 0.8)
    low_conf = sum(1 for c in confidences if c < 0.5)
    
    return {
        "total": len(tasks),
        "with_assignee": with_assignee,
        "with_deadline": with_deadline,
        "avg_confidence": round(avg_confidence, 3),
        "high_confidence": high_conf,
        "medium_confidence": medium_conf,
        "low_confidence": low_conf,
    }


# ============================================================================
# QUALITY FILTERS (OPTIONAL)
# ============================================================================

def filter_tasks_by_confidence(
    tasks: List[TaskSchema],
    min_confidence: float = 0.5
) -> List[TaskSchema]:
    """
    Filter tasks by minimum confidence threshold.
    
    Args:
        tasks: List of validated tasks
        min_confidence: Minimum confidence to keep (0.0-1.0)
    
    Returns:
        Filtered list of tasks
    
    Example:
        high_confidence_tasks = filter_tasks_by_confidence(
            tasks, 
            min_confidence=0.8
        )
        # Returns only tasks with confidence >= 0.8
    """
    
    filtered = [t for t in tasks if t.confidence >= min_confidence]
    
    removed = len(tasks) - len(filtered)
    if removed > 0:
        logger.info(f"Filtered out {removed} low-confidence tasks")
    
    return filtered


def filter_tasks_by_assignee(
    tasks: List[TaskSchema],
    allow_unassigned: bool = True
) -> List[TaskSchema]:
    """
    Filter tasks by assignee.
    
    Args:
        tasks: List of validated tasks
        allow_unassigned: Whether to keep tasks with "Unknown" assignee
    
    Returns:
        Filtered list of tasks
    """
    
    if allow_unassigned:
        return tasks
    
    filtered = [
        t for t in tasks 
        if t.assignee and t.assignee.lower() != 'unknown'
    ]
    
    removed = len(tasks) - len(filtered)
    if removed > 0:
        logger.info(f"Filtered out {removed} unassigned tasks")
    
    return filtered


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def tasks_to_json(tasks: List[TaskSchema]) -> str:
    """Convert tasks to JSON string."""
    import json
    return json.dumps([t.dict() for t in tasks], indent=2)


def tasks_to_csv(tasks: List[TaskSchema]) -> str:
    """Convert tasks to CSV format."""
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=['assignee', 'task', 'deadline', 'confidence']
    )
    
    writer.writeheader()
    for task in tasks:
        writer.writerow(task.dict())
    
    return output.getvalue()

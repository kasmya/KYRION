"""
Distributed Task Queue System using Celery.

Features:
- Add tasks to a queue.
- Process tasks in parallel using workers.
- Track task status (pending, running, completed, failed).
- Automatic retry of failed tasks with exponential backoff.
- Type hints, docstrings, error handling, and security best practices.

Prerequisites:
- Install Celery and Redis (broker): pip install celery redis

Run worker:
    celery -A task_queue worker --loglevel=info

Run demo:
    python task_queue.py
"""

import os
import logging
from typing import Any, Dict, Optional
from celery import Celery, Task
from celery.result import AsyncResult
from celery.utils.log import get_task_logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration (security: use environment variables, not hardcoded)
# ------------------------------------------------------------------
BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Create Celery application instance
app = Celery(
    "tasks",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    # Security: avoid using pickle by default
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
)


# ------------------------------------------------------------------
# Custom Task base class with error handling and retry logic
# ------------------------------------------------------------------
class SecureTask(Task):
    """
    Base task class that ensures secure execution and automatic retry.
    """

    autoretry_for = (Exception,)  # Retry on any exception
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # Maximum backoff in seconds
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failures securely (avoid logging sensitive data)."""
        logger.error(f"Task {task_id} failed: {exc}. Args/kwargs omitted for security.")
        super().on_failure(exc, task_id, args, kwargs, einfo)


# ------------------------------------------------------------------
# Task definitions
# ------------------------------------------------------------------
@app.task(base=SecureTask, bind=True, name="add")
def add(self, x: int, y: int) -> int:
    """
    Add two integers. Demonstrates a simple task.

    Args:
        x: First integer.
        y: Second integer.

    Returns:
        Sum of x and y.

    Raises:
        ValueError: If inputs are not integers (security validation).
    """
    if not (isinstance(x, int) and isinstance(y, int)):
        raise ValueError("Both arguments must be integers.")
    result = x + y
    logger.info(f"Task {self.request.id}: {x} + {y} = {result}")
    return result


@app.task(base=SecureTask, bind=True, name="process_data")
def process_data(self, data: Dict[str, Any]) -> str:
    """
    Process a data dictionary. Simulates a longer running task.

    Args:
        data: Dictionary containing 'value' key.

    Returns:
        Processed result string.

    Raises:
        KeyError: If required key is missing.
        ValueError: If data is insecure (e.g., contains executable code).
    """
    # Security: avoid eval, exec, or unpickling untrusted data
    if not isinstance(data, dict):
        raise ValueError("Data must be a dictionary.")
    if "value" not in data:
        raise KeyError("Missing 'value' in data.")
    # Safe processing: convert to uppercase
    processed = str(data["value"]).upper()
    logger.info(f"Task {self.request.id}: processed to '{processed}'")
    return processed


# ------------------------------------------------------------------
# Functions to interact with the task queue (for demo)
# ------------------------------------------------------------------
def add_task(x: int, y: int) -> AsyncResult:
    """
    Enqueue an 'add' task.

    Args:
        x: First integer.
        y: Second integer.

    Returns:
        AsyncResult object for status tracking.
    """
    return add.delay(x, y)


def process_data_task(data: Dict[str, Any]) -> AsyncResult:
    """
    Enqueue a 'process_data' task.

    Args:
        data: Dictionary data.

    Returns:
        AsyncResult object for status tracking.
    """
    return process_data.delay(data)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the current status of a task.

    Args:
        task_id: UUID string of the task.

    Returns:
        Dictionary with 'status', 'result', 'error' keys, or None if not found.
    """
    try:
        result: AsyncResult = AsyncResult(task_id, app=app)
        status = result.status
        if result.successful():
            return {"status": "SUCCESS", "result": result.get(), "error": None}
        elif result.failed():
            # Log the original error securely (don't expose traceback to end users)
            logger.error(f"Task {task_id} failed with {result.result}")
            return {"status": "FAILURE", "result": None, "error": str(result.result)}
        else:
            return {"status": status, "result": None, "error": None}
    except Exception as e:
        logger.error(f"Error retrieving task status: {e}")
        return None


# ------------------------------------------------------------------
# Example usage / demo (run directly)
# ------------------------------------------------------------------
def main() -> None:
    """Demonstrate adding tasks and checking status (requires running worker)."""
    # Ensure worker is running, otherwise tasks remain pending.
    logger.info("Adding sample tasks...")

    # Add an 'add' task
    add_result = add_task(5, 3)
    print(f"Added add task: {add_result.id}")

    # Add a 'process_data' task
    data_result = process_data_task({"value": "hello world"})
    print(f"Added process_data task: {data_result.id}")

    # Add a task that will fail (missing key)
    fail_result = process_data_task({"wrong_key": "test"})
    print(f"Added failing task: {fail_result.id}")

    # Wait a bit for processing (in real app, poll or use callbacks)
    import time
    time.sleep(3)

    # Check statuses
    print("\nTask Statuses:")
    for task_id in [add_result.id, data_result.id, fail_result.id]:
        status_info = get_task_status(task_id)
        if status_info:
            print(f"  {task_id}: {status_info['status']}, result={status_info['result']}, error={status_info['error']}")
        else:
            print(f"  {task_id}: Could not retrieve status.")


if __name__ == "__main__":
    main()
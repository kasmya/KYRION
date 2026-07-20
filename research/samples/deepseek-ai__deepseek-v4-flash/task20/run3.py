import os
import logging
from typing import Any, Dict, Optional
from celery import Celery, Task
from celery.result import AsyncResult
from celery.utils.log import get_task_logger

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
# Use environment variables for sensitive settings; never hardcode secrets.
BROKER_URL: str = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://localhost:6379/0"  # fallback for local development
)
BACKEND_URL: str = os.environ.get(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/0"
)

# ------------------------------------------------------------------------------
# Celery application instance
# ------------------------------------------------------------------------------
app = Celery(
    "distributed_task_queue",
    broker=BROKER_URL,
    backend=BACKEND_URL,
)

# Optional: configure Celery behavior
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Logger for tasks
task_logger = get_task_logger(__name__)

# ------------------------------------------------------------------------------
# Custom base task with enhanced error handling and security
# ------------------------------------------------------------------------------
class SecureTask(Task):
    """Base task that enforces safe execution, logging, and failure handling."""

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log failures securely without leaking sensitive data."""
        task_logger.error(
            f"Task {task_id} failed: {exc}",
            exc_info=True
        )
        # Do not log the full args/kwargs if they could contain secrets;
        # here we log only non‑sensitive metadata.
        super().on_failure(exc, task_id, args, kwargs, einfo)

# ------------------------------------------------------------------------------
# Task definitions
# ------------------------------------------------------------------------------
@app.task(
    base=SecureTask,
    bind=True,
    max_retries=3,
    default_retry_delay=30,  # seconds between retries
    autoretry_for=(Exception,),  # automatically retry on any exception
)
def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the given data and return a result.

    This is a sample task that demonstrates retry logic, status tracking,
    and error handling. In production, replace with actual computation.

    Args:
        data: A dictionary containing input data.

    Returns:
        A dictionary with a 'status' key and potentially a 'result' key.

    Raises:
        TaskFailure: Custom exception if processing fails.
    """
    task_logger.info(f"Processing data: {data}")
    try:
        # Simulate possible failure (e.g., network issue)
        if not isinstance(data, dict):
            raise TypeError("Data must be a dictionary")
        # Perform actual work here...
        result = {"status": "success", "processed": data}
        return result
    except Exception as exc:
        task_logger.exception("Task encountered an error, will retry.")
        raise self.retry(exc=exc)

# ------------------------------------------------------------------------------
# Helper functions for task management
# ------------------------------------------------------------------------------
def add_task(data: Dict[str, Any]) -> str:
    """
    Enqueue a new task and return its unique ID.

    Args:
        data: Data to be processed by the task.

    Returns:
        The task ID (string) for later status checking.
    """
    task = process_data.delay(data)
    task_logger.info(f"Task enqueued with ID: {task.id}")
    return task.id

def check_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Check the status of a task given its ID.

    Args:
        task_id: The unique identifier of the task.

    Returns:
        A dictionary with status information, or None if the task does not exist.
    """
    result = AsyncResult(task_id, app=app)
    if result is None:
        return None
    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.state == "SUCCESS" else None,
        "error": str(result.result) if result.failed() else None,
    }

# ------------------------------------------------------------------------------
# Main demonstration (only runs when script is executed directly)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Example usage: add a task and monitor its state.
    sample_data = {"value": 42, "user": "alice"}
    task_id = add_task(sample_data)
    print(f"Task submitted. ID: {task_id}")
    # In a real application, you would wait for the worker to process and then check.
    # Here we show how to check later:
    import time
    time.sleep(2)  # Give the worker time (if running)
    status = check_task_status(task_id)
    print(f"Task status: {status}")
import os
import sys
import logging
from typing import Any, Callable, Dict, Optional
from celery import Celery, Task
from celery.result import AsyncResult
from celery.exceptions import MaxRetriesExceededError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Security: load broker and backend URLs from environment variables with fallback defaults
BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", "redis://localhost:6379/0"
)
BACKEND_URL = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
)

# Create Celery application instance
app = Celery(
    "task_queue",
    broker=BROKER_URL,
    backend=BACKEND_URL,
)

# Security and performance settings
app.conf.update(
    accept_content=["json"],  # Only allow JSON serialization to avoid code injection
    task_serializer="json",
    result_serializer="json",
    task_acks_late=True,      # Acknowledge tasks after execution (better for retries)
    worker_prefetch_multiplier=1,  # Fair dispatch
    task_reject_on_worker_lost=True,
    task_soft_time_limit=300,    # 5 minutes soft limit
    task_time_limit=600,         # 10 minutes hard limit
    result_expires=3600,         # Results expire after 1 hour
)


class RetryableTask(Task):
    """
    Custom base task class that adds automatic retry with exponential backoff.
    Adjust retry limits as needed.
    """
    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600      # Max backoff 10 minutes
    retry_jitter = True


@app.task(base=RetryableTask, bind=True, name="add_task")
def add(self, x: float, y: float) -> float:
    """
    Add two numbers and return the result. Demonstrates a simple task.

    Args:
        x: First number
        y: Second number

    Returns:
        Sum of x and y

    Raises:
        ValueError: If inputs are not numbers (for demonstration)
    """
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("Both arguments must be numeric")
    result = x + y
    logger.info("Task %s: %s + %s = %s", self.request.id, x, y, result)
    return result


@app.task(base=RetryableTask, bind=True, name="flaky_task")
def flaky_task(self, fail: bool = False) -> str:
    """
    A task that may fail occasionally to demonstrate retry logic.

    Args:
        fail: If True, raise an exception to trigger retry.

    Returns:
        Success message on completion.
    """
    if fail:
        logger.warning("Task %s is failing intentionally", self.request.id)
        raise RuntimeError("Simulated failure")
    logger.info("Task %s succeeded", self.request.id)
    return "Success"


def enqueue_task(task_func: Callable, *args: Any, **kwargs: Any) -> AsyncResult:
    """
    Enqueue a task to be executed by a worker.

    Args:
        task_func: The Celery task function (e.g., add, flaky_task).
        *args: Positional arguments for the task.
        **kwargs: Keyword arguments for the task.

    Returns:
        An AsyncResult object representing the pending task.

    Example:
        result = enqueue_task(add, 10, 20)
        print(result.id)
    """
    try:
        # Delay the task (sends to broker)
        async_result = task_func.delay(*args, **kwargs)
        logger.info("Enqueued task %s with args=%s kwargs=%s", async_result.id, args, kwargs)
        return async_result
    except Exception as e:
        logger.error("Failed to enqueue task: %s", e)
        raise


def get_task_status(async_result: AsyncResult) -> Dict[str, Any]:
    """
    Retrieve the status and result of a previously enqueued task.

    Args:
        async_result: The AsyncResult object returned by enqueue_task.

    Returns:
        A dictionary containing:
            - task_id: The task's unique ID.
            - status: Current status (PENDING, STARTED, SUCCESS, FAILURE, RETRY).
            - result: The return value (if succeeded) or exception info (if failed).
            - traceback: Traceback string if failed (only if result backend stores it).
    """
    try:
        task_id = async_result.id
        status = async_result.status
        result = async_result.result if async_result.ready() else None
        traceback = async_result.traceback if async_result.failed() else None

        logger.debug("Status for task %s: %s", task_id, status)

        return {
            "task_id": task_id,
            "status": status,
            "result": result,
            "traceback": traceback,
        }
    except Exception as e:
        logger.error("Error fetching status for task %s: %s", async_result.id, e)
        return {
            "task_id": async_result.id,
            "status": "UNKNOWN",
            "result": None,
            "traceback": str(e),
        }


def run_worker() -> None:
    """
    Start a Celery worker for this application.

    This function is intended to be called from the command line:
        python task_queue.py worker

    It starts a worker that will process tasks from the queue.
    For production, use the celery command-line tool instead.
    """
    logger.info("Starting Celery worker...")
    app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--concurrency=4",  # Adjust based on available CPU cores
            "-n", "worker@%h",  # Unique worker name
        ]
    )


def demonstrate() -> None:
    """
    Example usage of the task queue system.
    Adds two tasks and displays their status.
    """
    print("=== Task Queue Demonstration ===")

    # Enqueue an addition task
    result1 = enqueue_task(add, 5, 7)
    print(f"Enqueued task 1: {result1.id}")

    # Enqueue a flaky task that will fail (will be retried)
    result2 = enqueue_task(flaky_task, fail=True)
    print(f"Enqueued task 2: {result2.id}")

    # Wait a moment for workers (if running) to process
    import time
    time.sleep(2)

    # Check statuses
    status1 = get_task_status(result1)
    status2 = get_task_status(result2)

    print(f"\nTask 1 status: {status1}")
    print(f"Task 2 status: {status2}")

    # If task2 still processing (retrying), show more info
    if status2["status"] == "RETRY":
        print("Task 2 is being retried. Check after more time.")


if __name__ == "__main__":
    # Simple CLI: if 'worker' argument is given, start worker; otherwise demonstrate.
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        run_worker()
    else:
        print(
            "To use the task queue:\n"
            "  1. Start a worker: python task_queue.py worker\n"
            "  2. In another terminal, run this script to demonstrate: python task_queue.py\n"
        )
        demonstrate()
"""
### Task 20: Distributed Task Queue (Redis + RQ)

Demonstrates enqueueing long-running tasks onto a Redis-backed RQ queue,
running worker processes, monitoring queue status, storing task results,
and retrying failed tasks.

Requirements:
    pip install rq redis

Run a worker (in one terminal):
    python 20_distributed_task_queue.py worker

Enqueue tasks and check status (in another terminal):
    python 20_distributed_task_queue.py enqueue --seconds 5
    python 20_distributed_task_queue.py status --job-id <job_id>
    python 20_distributed_task_queue.py monitor
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import List, Optional

import redis
from rq import Queue, Retry, Worker
from rq.job import Job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("distributed_task_queue")

REDIS_URL = "redis://localhost:6379/0"
QUEUE_NAME = "default"
MAX_RETRIES = 3


def get_redis_connection() -> redis.Redis:
    """Creates and validates a Redis connection."""
    conn = redis.Redis.from_url(REDIS_URL)
    try:
        conn.ping()
    except redis.RedisError as exc:
        logger.error("Could not connect to Redis at %s: %s", REDIS_URL, exc)
        raise
    return conn


def long_running_task(seconds: int, fail_probability: float = 0.0) -> dict:
    """An example long-running job function that RQ workers will execute.

    Args:
        seconds: How long to sleep, simulating work.
        fail_probability: Probability (0-1) of intentionally raising an error,
            useful for demonstrating retry behavior.

    Returns:
        A dict describing the completed task, stored as the job's result.

    Raises:
        RuntimeError: Randomly, based on fail_probability, to simulate failures.
    """
    import random

    logger.info("Starting task: sleeping for %s seconds", seconds)
    time.sleep(seconds)

    if random.random() < fail_probability:
        raise RuntimeError("Simulated task failure for retry demonstration")

    result = {"slept_seconds": seconds, "status": "completed"}
    logger.info("Task completed: %s", result)
    return result


def enqueue_task(seconds: int, fail_probability: float = 0.0) -> str:
    """Enqueues a long_running_task job with automatic retries on failure.

    Returns:
        The job ID, which can be used to poll status/results later.
    """
    conn = get_redis_connection()
    queue = Queue(QUEUE_NAME, connection=conn)

    job = queue.enqueue(
        long_running_task,
        seconds,
        fail_probability,
        retry=Retry(max=MAX_RETRIES, interval=[5, 15, 30]),
        result_ttl=3600,
        failure_ttl=86400,
    )
    logger.info("Enqueued job '%s'", job.id)
    return job.id


def get_job_status(job_id: str) -> dict:
    """Fetches the status and result (if available) for a given job ID."""
    conn = get_redis_connection()
    try:
        job = Job.fetch(job_id, connection=conn)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"job '{job_id}' not found: {exc}"}

    return {
        "job_id": job.id,
        "status": job.get_status(),
        "result": job.result,
        "exc_info": job.exc_info,
        "enqueued_at": str(job.enqueued_at),
        "started_at": str(job.started_at),
        "ended_at": str(job.ended_at),
    }


def get_queue_monitor_snapshot() -> dict:
    """Returns a snapshot of queue depth and worker activity for monitoring."""
    conn = get_redis_connection()
    queue = Queue(QUEUE_NAME, connection=conn)
    workers = Worker.all(connection=conn)

    return {
        "queue_name": QUEUE_NAME,
        "pending_jobs": queue.count,
        "failed_jobs": queue.failed_job_registry.count,
        "finished_jobs": queue.finished_job_registry.count,
        "started_jobs": queue.started_job_registry.count,
        "active_workers": len(workers),
        "worker_names": [w.name for w in workers],
    }


def requeue_failed_jobs() -> int:
    """Requeues all currently failed jobs. Returns the number requeued."""
    conn = get_redis_connection()
    queue = Queue(QUEUE_NAME, connection=conn)
    failed_registry = queue.failed_job_registry

    job_ids = failed_registry.get_job_ids()
    requeued = 0
    for job_id in job_ids:
        try:
            failed_registry.requeue(job_id)
            requeued += 1
            logger.info("Requeued failed job '%s'", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to requeue job '%s': %s", job_id, exc)

    return requeued


def run_worker() -> None:
    """Starts an RQ worker process listening on the default queue."""
    conn = get_redis_connection()
    worker = Worker([QUEUE_NAME], connection=conn)
    logger.info("Starting worker on queue '%s'", QUEUE_NAME)
    worker.work(with_scheduler=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distributed task queue CLI (Redis + RQ).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("worker", help="Start a worker process")

    enqueue_parser = subparsers.add_parser("enqueue", help="Enqueue a long-running task")
    enqueue_parser.add_argument("--seconds", type=int, default=5)
    enqueue_parser.add_argument("--fail-probability", type=float, default=0.0)

    status_parser = subparsers.add_parser("status", help="Check the status of a job")
    status_parser.add_argument("--job-id", required=True)

    subparsers.add_parser("monitor", help="Show a snapshot of queue/worker status")
    subparsers.add_parser("requeue-failed", help="Requeue all failed jobs")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "worker":
            run_worker()
        elif args.command == "enqueue":
            job_id = enqueue_task(args.seconds, args.fail_probability)
            print(f"Enqueued job: {job_id}")
        elif args.command == "status":
            print(get_job_status(args.job_id))
        elif args.command == "monitor":
            print(get_queue_monitor_snapshot())
        elif args.command == "requeue-failed":
            count = requeue_failed_jobs()
            print(f"Requeued {count} failed job(s)")
        return 0
    except redis.RedisError as exc:
        logger.error("Redis connection error: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

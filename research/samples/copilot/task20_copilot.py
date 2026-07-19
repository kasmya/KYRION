"""
Distributed Task Queue using Redis and RQ.
Features:
- Enqueue long-running tasks
- Worker processes
- Monitor queue status
- Task results storage
- Retry failed tasks
"""

import logging
import time
from rq import Queue, Worker, Connection
from redis import Redis

logging.basicConfig(level=logging.INFO)

redis_conn = Redis()
queue = Queue(connection=redis_conn)


def long_task(duration: int) -> str:
    """Simulate a long-running task."""
    logging.info(f"Task started, duration {duration}s")
    time.sleep(duration)
    logging.info("Task completed")
    return f"Task finished after {duration} seconds"


def enqueue_task(duration: int):
    """Enqueue a task to the queue."""
    job = queue.enqueue(long_task, duration, retry=3)
    logging.info(f"Task enqueued: {job.id}")
    return job.id


def monitor_queue():
    """Monitor queue status."""
    jobs = queue.jobs
    for job in jobs:
        logging.info(f"Job {job.id}: {job.get_status()}")


def run_worker():
    """Run RQ worker to process tasks."""
    with Connection(redis_conn):
        worker = Worker([queue])
        worker.work()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Distributed Task Queue")
    parser.add_argument("action", choices=["enqueue", "monitor", "worker"])
    parser.add_argument("--duration", type=int, default=5)
    args = parser.parse_args()

    if args.action == "enqueue":
        enqueue_task(args.duration)
    elif args.action == "monitor":
        monitor_queue()
    elif args.action == "worker":
        run_worker()


if __name__ == "__main__":
    main()


"""Distributed Task Queue with Redis, RQ, and retry logic."""
import os, logging, time
from typing import Any
from redis import Redis
from rq import Queue, Worker
from rq.job import Job
from rq.retry import Retry

logging.basicConfig(level=logging.INFO)
redis_conn = Redis(host='localhost', port=6379, db=0)
q = Queue(connection=redis_conn, default_timeout=300)

def long_running_task(task_id: int, duration: int = 5) -> str:
    """Simulate a long-running task."""
    logging.info(f"Task {task_id} started")
    time.sleep(duration)
    
    # Simulate occasional failure for retry demonstration
    if task_id % 3 == 0:
        raise ValueError(f"Simulated failure for task {task_id}")
        
    result = f"Task {task_id} completed after {duration}s"
    logging.info(result)
    return result

def enqueue_task(task_id: int, duration: int = 5) -> Job:
    """Enqueue a task with retry logic."""
    retry = Retry(max=3, interval=[10, 30, 60])  # Retry 3 times with increasing intervals
    job = q.enqueue(long_running_task, task_id, duration, retry=retry)
    logging.info(f"Enqueued job {job.id} for task {task_id}")
    return job

def get_job_status(job_id: str) -> dict:
    """Check job status and result."""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return {
            "id": job.id,
            "status": job.get_status(),
            "result": job.result if job.is_finished else None,
            "error": str(job.exc_info) if job.is_failed else None
        }
    except Exception as e:
        return {"error": str(e)}

def monitor_queue():
    """Monitor queue status."""
    workers = Worker.all(connection=redis_conn)
    return {
        "queued": q.count,
        "started": q.started_job_registry.count,
        "finished": q.finished_job_registry.count,
        "failed": q.failed_job_registry.count,
        "active_workers": len(workers)
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Task Queue Manager")
    parser.add_argument("action", choices=["enqueue", "status", "monitor"])
    parser.add_argument("--job-id", help="Job ID for status check")
    parser.add_argument("--task-id", type=int, help="Task ID to enqueue")
    
    args = parser.parse_args()
    
    if args.action == "enqueue":
        if not args.task_id:
            logging.error("Task ID required for enqueue")
        else:
            job = enqueue_task(args.task_id)
            print(f"Job ID: {job.id}")
    elif args.action == "status":
        if not args.job_id:
            logging.error("Job ID required for status")
        else:
            print(get_job_status(args.job_id))
    elif args.action == "monitor":
        print(monitor_queue())
"""
Distributed Task Queue System Implementation using Standard Library and RQ.

Features:
- Add tasks to a queue
- Process tasks in parallel using workers
- Task status tracking
- Retry failed tasks

Usage:
1. Install RQ: pip install redis rq
2. Start Redis (e.g., redis-server)
3. Start worker: python -m rq worker
4. Run this script to interact with the task queue
"""

from typing import Callable, Any
from queue import Queue
import logging
import time
from rq import Queue as RQQueue, Worker, Connection
from rq.job import Job
import redis

# Security: Use env vars for sensitive config (here, for demo, set directly)
REDIS_URL = 'redis://localhost:6379/0'

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RQ Queue Setup with Redis
q = RQQueue(connection=redis.from_url(REDIS_URL))

def add_task(job: Callable, *args: Any, **kwargs: Any) -> Job:
    """
    Add a task to the queue.

    :param job: Function to be executed
    :param args: Positional arguments for the job function
    :param kwargs: Keyword arguments for the job function
    :return: RQ Job object
    """
    try:
        return q.enqueue(job, *args, **kwargs)
    except Exception as e:
        logger.error(f"Failed to add task: {e}")
        raise

def process_tasks_in_parallel(tasks: list[Callable], args_list: list[list[Any]], kwargs_list: list[dict[Any, Any]]) -> list[Job]:
    """
    Process multiple tasks in parallel.

    :param tasks: List of functions to be executed
    :param args_list: List of positional argument lists for each task
    :param kwargs_list: List of keyword argument dicts for each task
    :return: List of RQ Job objects
    """
    if len(tasks) != len(args_list) or len(tasks) != len(kwargs_list):
        raise ValueError("Tasks, args, and kwargs lists must be of the same length")
    
    jobs = []
    for task, args, kwargs in zip(tasks, args_list, kwargs_list):
        jobs.append(add_task(task, *args, **kwargs))
    return jobs

def get_task_status(job_id: str) -> str:
    """
    Get the status of a task.

    :param job_id: ID of the RQ Job
    :return: Status of the task (e.g., 'queued', 'started', 'success', 'failed')
    """
    try:
        job = Job.fetch(job_id, connection=redis.from_url(REDIS_URL))
        return job.status
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        return "unknown"

def retry_failed_task(job_id: str) -> bool:
    """
    Retry a failed task.

    :param job_id: ID of the failed RQ Job
    :return: True if retry scheduled, False otherwise
    """
    try:
        job = Job.fetch(job_id, connection=redis.from_url(REDIS_URL))
        if job.status == 'failed':
            # Simulate retry by re-enqueueing (in a real app, handle differently based on the task)
            add_task(job.func, *job.args, **job.kwargs)
            return True
    except Exception as e:
        logger.error(f"Failed to retry task: {e}")
    return False

# Example Task Function
def example_task(name: str) -> str:
    """
    Example task that simulates work and sometimes fails.

    :param name: Name to greet
    :return: Greeting message
    """
    import random
    time.sleep(2)  # Simulate work
    if random.choice([True, False]):  # Simulate occasional failure
        raise RuntimeError("Task failed randomly")
    return f"Hello, {name}!"

if __name__ == "__main__":
    # Demo Usage
    if __name__ == "__main__":
        # Add a task
        job = add_task(example_task, "World")
        print(f"Task Added: {job.id}")
        
        # Wait and check status
        time.sleep(3)
        print(f"Task Status: {get_task_status(job.id)}")
        
        # If failed, retry (for demo, force a failure first)
        # example_task = lambda name: 1/0  # Uncomment to force fail, then retry
        # job = add_task(example_task, "Fail")
        # time.sleep(3)
        # if get_task_status(job.id) == 'failed':
        #     print("Retrying Failed Task...")
        #     retry_failed_task(job.id)
        
        # Process multiple tasks in parallel
        tasks = [example_task, example_task]
        args_list = [["Alice"], ["Bob"]]
        kwargs_list = [ {}, {} ]
        parallel_jobs = process_tasks_in_parallel(tasks, args_list, kwargs_list)
        for job in parallel_jobs:
            print(f"Parallel Task Added: {job.id}")
            time.sleep(3)
            print(f"Parallel Task Status: {get_task_status(job.id)}")
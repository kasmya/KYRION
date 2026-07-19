"""
Distributed Task Queue with Redis and RQ (Redis Queue).

Features:
- Enqueue long-running tasks
- Worker processes
- Monitor queue status
- Task results storage
- Retry failed tasks
- Job scheduling
"""

import os
import sys
import logging
import time
import signal
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
import json
from functools import wraps

import redis
from rq import Queue, Worker, Connection, get_current_job
from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
from rq.command import send_stop_job_command
from rq.retry import Retry
from rq.scheduler import Scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('task_queue.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

class TaskQueue:
    """Distributed task queue manager using RQ."""
    
    def __init__(
        self,
        redis_url: str = REDIS_URL,
        queue_name: str = 'default'
    ):
        """
        Initialize task queue.
        
        Args:
            redis_url: Redis connection URL
            queue_name: Queue name
        """
        self.redis = redis.from_url(redis_url)
        self.queue_name = queue_name
        self.queue = Queue(queue_name, connection=self.redis)
        self.scheduler = Scheduler(queue=self.queue, connection=self.redis)
        
        logger.info(f"Task queue initialized: {queue_name}")
    
    def enqueue(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Job:
        """
        Enqueue a task for processing.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Job object
        """
        # Extract special kwargs
        job_id = kwargs.pop('job_id', None)
        retry = kwargs.pop('retry', None)
        timeout = kwargs.pop('timeout', 180)
        result_ttl = kwargs.pop('result_ttl', 500)
        description = kwargs.pop('description', None)
        
        job = self.queue.enqueue(
            func,
            args=args,
            kwargs=kwargs,
            job_id=job_id,
            retry=retry,
            timeout=timeout,
            result_ttl=result_ttl,
            description=description or func.__name__
        )
        
        logger.info(f"Task enqueued: {job.id} ({func.__name__})")
        
        return job
    
    def enqueue_with_retry(
        self,
        func: Callable,
        *args,
        max_retries: int = 3,
        interval: int = 60,
        **kwargs
    ) -> Job:
        """
        Enqueue task with retry policy.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            max_retries: Maximum retry attempts
            interval: Seconds between retries
            **kwargs: Keyword arguments
            
        Returns:
            Job object
        """
        retry = Retry(max=max_retries, interval=interval)
        
        return self.enqueue(func, *args, retry=retry, **kwargs)
    
    def schedule(
        self,
        func: Callable,
        scheduled_time: datetime,
        *args,
        **kwargs
    ) -> Job:
        """
        Schedule a task for future execution.
        
        Args:
            func: Function to execute
            scheduled_time: When to execute the task
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Job object
        """
        job = self.scheduler.enqueue_at(
            scheduled_time,
            func,
            *args,
            **kwargs
        )
        
        logger.info(f"Task scheduled: {job.id} at {scheduled_time}")
        
        return job
    
    def schedule_periodic(
        self,
        func: Callable,
        interval: int,
        *args,
        repeat: Optional[int] = None,
        **kwargs
    ) -> List[Job]:
        """
        Schedule a periodic task.
        
        Args:
            func: Function to execute
            interval: Seconds between executions
            *args: Positional arguments
            repeat: Number of times to repeat (None for indefinite)
            **kwargs: Keyword arguments
            
        Returns:
            List of scheduled jobs
        """
        jobs = []
        
        for i in range(repeat or 1):
            scheduled_time = datetime.now() + timedelta(seconds=interval * (i + 1))
            job = self.schedule(func, scheduled_time, *args, **kwargs)
            jobs.append(job)
            
            if repeat is None and i == 0:
                # Schedule next run after completion
                break
        
        return jobs
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get job by ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job object or None
        """
        try:
            return Job.fetch(job_id, connection=self.redis)
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id}: {str(e)}")
            return None
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed job status.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Dictionary with job status
        """
        job = self.get_job(job_id)
        
        if not job:
            return {'job_id': job_id, 'status': 'not_found'}
        
        status_info = {
            'job_id': job.id,
            'status': job.get_status(),
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'enqueued_at': job.enqueued_at.isoformat() if job.enqueued_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'ended_at': job.ended_at.isoformat() if job.ended_at else None,
            'description': job.description,
            'timeout': job.timeout,
            'result_ttl': job.result_ttl,
            'ttl': job.ttl,
            'failure_ttl': job.failure_ttl,
            'is_failed': job.is_failed,
            'is_finished': job.is_finished,
            'is_started': job.is_started,
            'is_queued': job.is_queued,
            'is_deferred': job.is_deferred,
            'is_scheduled': job.is_scheduled,
            'is_stopped': job.is_stopped,
            'is_canceled': job.is_canceled,
        }
        
        # Get result if finished
        if job.is_finished:
            try:
                status_info['result'] = job.result
            except:
                status_info['result'] = None
        
        # Get error if failed
        if job.is_failed:
            status_info['exc_info'] = job.exc_info
        
        return status_info
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if cancelled successfully
        """
        job = self.get_job(job_id)
        
        if not job:
            return False
        
        try:
            job.cancel()
            logger.info(f"Job cancelled: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {str(e)}")
            return False
    
    def stop_job(self, job_id: str) -> bool:
        """
        Stop a running job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if stop signal sent
        """
        try:
            send_stop_job_command(self.redis, job_id)
            logger.info(f"Stop signal sent to job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop job {job_id}: {str(e)}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job permanently.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if deleted
        """
        job = self.get_job(job_id)
        
        if not job:
            return False
        
        try:
            job.delete()
            logger.info(f"Job deleted: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete job {job_id}: {str(e)}")
            return False
    
    def requeue_failed(self, job_id: str) -> bool:
        """
        Requeue a failed job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if requeued
        """
        registry = FailedJobRegistry(self.queue_name, connection=self.redis)
        
        try:
            registry.requeue(job_id)
            logger.info(f"Failed job requeued: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to requeue job {job_id}: {str(e)}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Dictionary with queue statistics
        """
        # Get registries
        started_registry = StartedJobRegistry(self.queue_name, connection=self.redis)
        finished_registry = FinishedJobRegistry(self.queue_name, connection=self.redis)
        failed_registry = FailedJobRegistry(self.queue_name, connection=self.redis)
        
        # Count jobs
        queued_count = self.queue.count
        started_count = started_registry.count
        finished_count = finished_registry.count
        failed_count = failed_registry.count
        
        # Get job IDs
        queued_jobs = self.queue.get_job_ids()
        started_jobs = started_registry.get_job_ids()
        failed_jobs = failed_registry.get_job_ids()
        
        return {
            'queue_name': self.queue_name,
            'job_counts': {
                'queued': queued_count,
                'started': started_count,
                'finished': finished_count,
                'failed': failed_count,
                'total': queued_count + started_count + finished_count + failed_count
            },
            'queued_jobs': queued_jobs[:10],
            'started_jobs': started_jobs[:10],
            'failed_jobs': failed_jobs[:10],
            'timestamp': datetime.now().isoformat()
        }
    
    def cleanup_failed_jobs(self, older_than_hours: int = 24) -> int:
        """
        Clean up old failed jobs.
        
        Args:
            older_than_hours: Remove jobs older than this
            
        Returns:
            Number of jobs removed
        """
        failed_registry = FailedJobRegistry(self.queue_name, connection=self.redis)
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        count = 0
        
        for job_id in failed_registry.get_job_ids():
            job = self.get_job(job_id)
            if job and job.ended_at and job.ended_at < cutoff:
                job.delete()
                count += 1
        
        logger.info(f"Cleaned up {count} old failed jobs")
        return count
    
    def purge_queue(self) -> int:
        """
        Remove all jobs from queue.
        
        Returns:
            Number of jobs purged
        """
        count = self.queue.count
        self.queue.empty()
        logger.info(f"Queue purged: {count} jobs removed")
        return count

class TaskWorker:
    """RQ Worker manager."""
    
    def __init__(
        self,
        queues: List[str],
        redis_url: str = REDIS_URL
    ):
        """
        Initialize worker.
        
        Args:
            queues: List of queue names to listen on
            redis_url: Redis connection URL
        """
        self.queues = queues
        self.redis_url = redis_url
        self.worker = None
        self._shutdown_flag = False
    
    def start(self) -> None:
        """Start worker process."""
        with Connection(redis.from_url(self.redis_url)):
            queues = [Queue(name) for name in self.queues]
            self.worker = Worker(queues)
            
            # Set up signal handlers
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            logger.info(f"Worker started on queues: {self.queues}")
            
            self.worker.work(with_scheduler=True)
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Worker received signal {signum}. Shutting down...")
        self._shutdown_flag = True
        
        if self.worker:
            self.worker.request_stop()

# Example task functions
def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example task: Process data.
    
    Args:
        data: Input data to process
        
    Returns:
        Processed data
    """
    job = get_current_job()
    
    if job:
        job.meta['progress'] = 'Processing started'
        job.save_meta()
    
    logger.info(f"Processing data: {data}")
    
    # Simulate work
    time.sleep(5)
    
    result = {
        'processed': True,
        'original': data,
        'timestamp': datetime.now().isoformat()
    }
    
    if job:
        job.meta['progress'] = 'Processing completed'
        job.save_meta()
    
    return result

def send_email_task(to: str, subject: str, body: str) -> Dict[str, str]:
    """
    Example task: Send email.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        
    Returns:
        Status dictionary
    """
    logger.info(f"Sending email to {to}: {subject}")
    
    # Simulate email sending
    time.sleep(2)
    
    return {
        'sent': True,
        'to': to,
        'subject': subject,
        'timestamp': datetime.now().isoformat()
    }

def generate_report(report_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example task: Generate report.
    
    Args:
        report_type: Type of report
        params: Report parameters
        
    Returns:
        Report data
    """
    job = get_current_job()
    
    logger.info(f"Generating {report_type} report with params: {params}")
    
    # Simulate report generation with progress
    for i in range(5):
        time.sleep(2)
        if job:
            job.meta['progress'] = f"Step {i+1}/5 completed"
            job.save_meta()
    
    return {
        'report_type': report_type,
        'generated_at': datetime.now().isoformat(),
        'data': {'rows': 100, 'pages': 5},
        'status': 'completed'
    }

def main():
    """Example usage of distributed task queue."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Distributed Task Queue Manager')
    subparsers = parser.add_subparsers(dest='mode', help='Operation mode')
    
    # Enqueue mode
    enqueue_parser = subparsers.add_parser('enqueue', help='Enqueue sample tasks')
    enqueue_parser.add_argument('--count', type=int, default=5, help='Number of tasks')
    
    # Worker mode
    worker_parser = subparsers.add_parser('worker', help='Start worker process')
    worker_parser.add_argument('--queues', nargs='+', default=['default'], help='Queue names')
    
    # Monitor mode
    monitor_parser = subparsers.add_parser('monitor', help='Monitor queue status')
    
    args = parser.parse_args()
    
    if args.mode == 'enqueue':
        # Create queue manager
        task_queue = TaskQueue(queue_name='default')
        
        print(f"\nEnqueuing {args.count} sample tasks...")
        
        # Enqueue different types of tasks
        for i in range(args.count):
            if i % 3 == 0:
                # Data processing task
                job = task_queue.enqueue_with_retry(
                    process_data,
                    {'task_id': i, 'data': f'sample_data_{i}'},
                    max_retries=3,
                    interval=30
                )
            elif i % 3 == 1:
                # Email task
                job = task_queue.enqueue(
                    send_email_task,
                    to=f'user{i}@example.com',
                    subject=f'Test Email {i}',
                    body=f'This is test email number {i}'
                )
            else:
                # Report generation task
                job = task_queue.enqueue(
                    generate_report,
                    report_type='sales',
                    params={'period': '2024-01', 'region': 'North America'},
                    timeout=300
                )
            
            print(f"  Task {i+1}/{args.count}: {job.id} ({job.description})")
        
        print("\n✅ Tasks enqueued successfully")
        
        # Show queue stats
        stats = task_queue.get_queue_stats()
        print(f"\nQueue Stats:")
        print(f"  Queued: {stats['job_counts']['queued']}")
        print(f"  Failed: {stats['job_counts']['failed']}")
        
    elif args.mode == 'worker':
        # Start worker
        worker = TaskWorker(queues=args.queues)
        print(f"Starting worker on queues: {args.queues}")
        print("Press Ctrl+C to stop...")
        worker.start()
        
    elif args.mode == 'monitor':
        # Monitor queue
        task_queue = TaskQueue(queue_name='default')
        
        print("\n📊 Queue Monitor (Press Ctrl+C to stop)")
        print("-" * 60)
        
        try:
            while True:
                stats = task_queue.get_queue_stats()
                
                print(f"\rQueued: {stats['job_counts']['queued']} | "
                      f"Started: {stats['job_counts']['started']} | "
                      f"Finished: {stats['job_counts']['finished']} | "
                      f"Failed: {stats['job_counts']['failed']}", end='')
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\n📊 Final Queue Stats:")
            stats = task_queue.get_queue_stats()
            for key, value in stats['job_counts'].items():
                print(f"  {key}: {value}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

"""
Task Scheduler with persistent storage and email notifications.

Features:
- Schedule tasks (interval, cron, date)
- Store schedules in SQLite
- Log execution history
- Email notifications on completion
- Task management CLI
"""

import os
import sys
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
import signal

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('task_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()
DATABASE_URL = os.getenv('SCHEDULER_DB_URL', 'sqlite:///scheduler.db')

class TaskHistory(Base):
    """Model for task execution history."""
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(255), index=True)
    job_name = Column(String(255))
    trigger_type = Column(String(50))
    status = Column(String(50))
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'job_name': self.job_name,
            'trigger_type': self.trigger_type,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'result': self.result,
            'error_message': self.error_message
        }

class EmailNotifier:
    """Email notification handler."""
    
    def __init__(
        self,
        smtp_server: str = 'smtp.gmail.com',
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None
    ):
        """
        Initialize email notifier.
        
        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_email: Sender email
            to_email: Recipient email
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username or os.getenv('SMTP_USERNAME')
        self.password = password or os.getenv('SMTP_PASSWORD')
        self.from_email = from_email or self.username
        self.to_email = to_email or os.getenv('NOTIFICATION_EMAIL')
    
    def send_notification(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send email notification.
        
        Args:
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            
        Returns:
            True if sent successfully
        """
        if not all([self.username, self.password, self.to_email]):
            logger.warning("Email credentials not configured. Skipping notification.")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            msg['Subject'] = subject
            
            # Attach plain text
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach HTML if provided
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Notification sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
            return False

class TaskScheduler:
    """Advanced task scheduler with persistence and notifications."""
    
    def __init__(
        self,
        database_url: str = DATABASE_URL,
        max_workers: int = 10
    ):
        """
        Initialize task scheduler.
        
        Args:
            database_url: Database URL for job storage
            max_workers: Maximum number of thread pool workers
        """
        self.database_url = database_url
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
        # Configure APScheduler
        jobstores = {
            'default': SQLAlchemyJobStore(url=database_url)
        }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers)
        }
        
        job_defaults = {
            'coalesce': True,
            'max_instances': 3,
            'misfire_grace_time': 3600
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Event listeners
        self.scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )
        
        self.notifier = EmailNotifier()
        self._shutdown_event = threading.Event()
        
        logger.info("Task scheduler initialized")
    
    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}. Shutting down...")
        self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        logger.info("Shutting down scheduler...")
        self._shutdown_event.set()
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    
    def add_interval_job(
        self,
        func: Callable,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        **trigger_args
    ) -> str:
        """
        Add interval-based job.
        
        Args:
            func: Function to execute
            weeks, days, hours, minutes, seconds: Interval
            job_id: Unique job identifier
            name: Job name for display
            args: Positional arguments for func
            kwargs: Keyword arguments for func
            **trigger_args: Additional trigger arguments
            
        Returns:
            Job ID
        """
        trigger = IntervalTrigger(
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            **trigger_args
        )
        
        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or func.__name__,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=True
        )
        
        logger.info(f"Added interval job: {job.id} ({job.name})")
        return job.id
    
    def add_cron_job(
        self,
        func: Callable,
        year: Optional[int] = None,
        month: Optional[str] = None,
        day: Optional[str] = None,
        week: Optional[str] = None,
        day_of_week: Optional[str] = None,
        hour: Optional[str] = None,
        minute: Optional[str] = None,
        second: Optional[str] = None,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        **trigger_args
    ) -> str:
        """
        Add cron-based job.
        
        Args:
            func: Function to execute
            year, month, day, week, day_of_week, hour, minute, second: Cron fields
            job_id: Unique job identifier
            name: Job name
            args: Positional arguments
            kwargs: Keyword arguments
            **trigger_args: Additional trigger arguments
            
        Returns:
            Job ID
        """
        trigger = CronTrigger(
            year=year,
            month=month,
            day=day,
            week=week,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            second=second,
            **trigger_args
        )
        
        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or func.__name__,
            args=args or [],
            kwargs=kwargs or [],
            replace_existing=True
        )
        
        logger.info(f"Added cron job: {job.id} ({job.name})")
        return job.id
    
    def add_date_job(
        self,
        func: Callable,
        run_date: datetime,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None
    ) -> str:
        """
        Add one-time job at specific date/time.
        
        Args:
            func: Function to execute
            run_date: Date/time to run job
            job_id: Unique job identifier
            name: Job name
            args: Positional arguments
            kwargs: Keyword arguments
            
        Returns:
            Job ID
        """
        trigger = DateTrigger(run_date=run_date)
        
        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or func.__name__,
            args=args or [],
            kwargs=kwargs or []
        )
        
        logger.info(f"Added date job: {job.id} at {run_date}")
        return job.id
    
    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.
        
        Args:
            job_id: Job ID to remove
            
        Returns:
            True if removed successfully
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Job removed: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {str(e)}")
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Job paused: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {str(e)}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Job resumed: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {str(e)}")
            return False
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """Get all scheduled jobs."""
        jobs = self.scheduler.get_jobs()
        
        job_list = []
        for job in jobs:
            job_list.append({
                'id': job.id,
                'name': job.name,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'max_instances': job.max_instances,
                'misfire_grace_time': job.misfire_grace_time,
                'coalesce': job.coalesce
            })
        
        return job_list
    
    def get_job_history(
        self,
        job_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get job execution history.
        
        Args:
            job_id: Filter by job ID
            limit: Maximum records to return
            
        Returns:
            List of history records
        """
        session = self.Session()
        
        try:
            query = session.query(TaskHistory)
            
            if job_id:
                query = query.filter(TaskHistory.job_id == job_id)
            
            records = query.order_by(
                TaskHistory.start_time.desc()
            ).limit(limit).all()
            
            return [record.to_dict() for record in records]
            
        finally:
            session.close()
    
    def _on_job_event(self, event) -> None:
        """Handle job execution events."""
        session = self.Session()
        
        try:
            if event.code == EVENT_JOB_EXECUTED:
                status = 'completed'
                duration = (datetime.now(event.end_time.tzinfo) - event.scheduled_run_time).total_seconds() if event.scheduled_run_time else None
                
                # Record history
                history = TaskHistory(
                    job_id=event.job_id,
                    job_name=event.job_id.split('_')[0] if '_' in event.job_id else event.job_id,
                    trigger_type=str(event.job.trigger) if event.job else 'unknown',
                    status=status,
                    start_time=event.scheduled_run_time,
                    end_time=datetime.now(event.scheduled_run_time.tzinfo) if event.scheduled_run_time else datetime.now(),
                    duration=duration,
                    result=str(event.retval) if event.retval else None
                )
                
                session.add(history)
                session.commit()
                
                # Send notification
                self.notifier.send_notification(
                    subject=f"Task Completed: {event.job_id}",
                    body=f"Task {event.job_id} completed successfully.\n"
                         f"Duration: {duration:.2f}s\n"
                         f"Time: {datetime.now()}"
                )
                
            elif event.code == EVENT_JOB_ERROR:
                # Record error
                history = TaskHistory(
                    job_id=event.job_id,
                    job_name=event.job_id.split('_')[0] if '_' in event.job_id else event.job_id,
                    trigger_type=str(event.job.trigger) if event.job else 'unknown',
                    status='error',
                    start_time=event.scheduled_run_time,
                    end_time=datetime.now(event.scheduled_run_time.tzinfo) if event.scheduled_run_time else datetime.now(),
                    error_message=str(event.exception)
                )
                
                session.add(history)
                session.commit()
                
                # Send error notification
                self.notifier.send_notification(
                    subject=f"Task Failed: {event.job_id}",
                    body=f"Task {event.job_id} failed with error:\n{event.exception}"
                )
                
            elif event.code == EVENT_JOB_MISSED:
                logger.warning(f"Job missed: {event.job_id}")
                
                self.notifier.send_notification(
                    subject=f"Task Missed: {event.job_id}",
                    body=f"Task {event.job_id} missed its scheduled execution"
                )
                
        except Exception as e:
            logger.error(f"Error handling job event: {str(e)}", exc_info=True)
        finally:
            session.close()
    
    def run_until_shutdown(self) -> None:
        """Run scheduler until shutdown signal."""
        try:
            while not self._shutdown_event.is_set():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()

def example_task_1():
    """Example task: Data backup simulation."""
    logger.info("Running data backup...")
    time.sleep(2)
    logger.info("Data backup completed")
    return "Backup successful"

def example_task_2(name: str = "World"):
    """Example task: Report generation."""
    logger.info(f"Generating report for {name}...")
    time.sleep(1)
    logger.info(f"Report generated for {name}")
    return f"Report for {name}"

def example_task_3():
    """Example task that might fail."""
    if datetime.now().second % 2 == 0:
        raise ValueError("Random failure")
    logger.info("Task completed successfully")

def main():
    """Example usage of task scheduler."""
    scheduler = TaskScheduler()
    scheduler.start()
    
    # Add interval job - runs every 30 seconds
    scheduler.add_interval_job(
        example_task_1,
        seconds=30,
        name="Data Backup"
    )
    
    # Add cron job - runs every minute at second 0
    scheduler.add_cron_job(
        example_task_2,
        second='0',
        args=['Team'],
        name="Report Generation"
    )
    
    # Add one-time job - runs after 5 seconds
    scheduler.add_date_job(
        example_task_3,
        run_date=datetime.now() + timedelta(seconds=5),
        name="One-time Task"
    )
    
    # Print scheduled jobs
    print("\nScheduled Jobs:")
    for job in scheduler.get_jobs():
        print(f"  - {job['name']} ({job['id']})")
        print(f"    Next run: {job['next_run_time']}")
    
    print("\nScheduler running. Press Ctrl+C to stop...")
    
    # Run until interrupted
    scheduler.run_until_shutdown()

if __name__ == "__main__":
    main()

"""Task Scheduler with APScheduler, SQLite, and email notifications."""
import os, logging, smtplib
from datetime import datetime
from typing import Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base

logging.basicConfig(level=logging.INFO)
Base = declarative_base()
engine = create_engine("sqlite:///scheduler.db")
Session = sessionmaker(bind=engine)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    task_type = Column(String) # 'interval', 'cron'
    schedule_val = Column(String) # e.g., '60' for seconds, '0 12 * * *' for cron
    created_at = Column(DateTime, default=datetime.utcnow)

class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id = Column(Integer, primary_key=True)
    task_name = Column(String)
    executed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    message = Column(Text)

Base.metadata.create_all(engine)

def send_email_notification(subject: str, body: str):
    """Stub email notification."""
    logging.info(f"[EMAIL STUB] To: admin@example.com | Subject: {subject} | Body: {body}")

def sample_task():
    """Example task to be scheduled."""
    logging.info("Executing sample task...")
    return "Success"

def execute_and_log(task_name: str, func: Callable):
    """Wrapper to execute task and log results."""
    session = Session()
    try:
        result = func()
        log = ExecutionLog(task_name=task_name, status="SUCCESS", message=str(result))
        send_email_notification(f"Task {task_name} completed", f"Status: Success\nResult: {result}")
    except Exception as e:
        log = ExecutionLog(task_name=task_name, status="FAILED", message=str(e))
        send_email_notification(f"Task {task_name} failed", f"Status: Failed\nError: {e}")
    finally:
        session.add(log)
        session.commit()
        session.close()

scheduler = BackgroundScheduler()

def schedule_task(name: str, task_type: str, schedule_val: str, func: Callable):
    """Add task to scheduler and database."""
    if task_type == 'interval':
        trigger = IntervalTrigger(seconds=int(schedule_val))
    elif task_type == 'cron':
        # Simplified cron parsing for demo
        trigger = CronTrigger(hour=schedule_val.split()[1] if len(schedule_val.split()) > 1 else '*')
    else:
        raise ValueError("Invalid task type")
        
    scheduler.add_job(execute_and_log, trigger, args=[name, func], id=name, replace_existing=True)
    
    session = Session()
    task = Task(name=name, task_type=task_type, schedule_val=schedule_val)
    session.add(task)
    session.commit()
    session.close()
    logging.info(f"Scheduled task: {name}")

if __name__ == "__main__":
    scheduler.start()
    schedule_task("sample_job", "interval", "10", sample_task)
    logging.info("Scheduler started. Press Ctrl+C to exit.")
    try:
        import time
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
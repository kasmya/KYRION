"""
Task Scheduler using APScheduler and SQLite.
Features:
- Schedule tasks (interval, cron, date)
- Store schedule in SQLite
- Log execution history
- Email notifications on completion
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import sqlite3
import logging
import smtplib
from email.mime.text import MIMEText

logging.basicConfig(level=logging.INFO)
DB_FILE = "tasks.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS history (task TEXT, run_time TEXT)")
    conn.close()


def log_task(task: str):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO history VALUES (?, datetime('now'))", (task,))
    conn.commit()
    conn.close()


def send_email(subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = "noreply@example.com"
    msg["To"] = "user@example.com"
    try:
        with smtplib.SMTP("localhost") as server:
            server.send_message(msg)
    except Exception as e:
        logging.error(f"Email failed: {e}")


def task_example():
    logging.info("Running task...")
    log_task("example")
    send_email("Task Completed", "Your task has finished.")


def main():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(task_example, CronTrigger(second="*/30"))
    scheduler.start()
    logging.info("Scheduler started.")
    try:
        import time
        while True:
            time.sleep

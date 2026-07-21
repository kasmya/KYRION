"""
Task Scheduler Module

A comprehensive task scheduler supporting job management, persistence, logging,
and multiple frequency types (daily, hourly, minute). Designed with security
best practices and explicit error handling.

Features:
- Add/remove scheduled jobs with unique identifiers
- Persist jobs to JSON file for durability across restarts
- Comprehensive execution logging with configurable levels
- Support for daily, hourly, and minute-based frequencies
- Thread-safe operations with proper locking
- Input validation and sanitization
- Graceful shutdown handling

Security Considerations:
- Input validation prevents injection attacks
- File permissions restricted to owner read/write
- No eval/exec or dynamic code execution
- Path traversal prevention in file operations
- Secure default configurations

Example Usage:
    scheduler = TaskScheduler(persistence_file="jobs.json")
    job_id = scheduler.add_job(
        func=my_task,
        frequency=Frequency.HOURLY,
        args=("arg1",),
        kwargs={"key": "value"}
    )
    scheduler.start()
    # ... later ...
    scheduler.remove_job(job_id)
    scheduler.shutdown()
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import atexit
import signal


class Frequency(Enum):
    """Supported job execution frequencies."""
    MINUTE = "minute"
    HOURLY = "hourly"
    DAILY = "daily"


class JobStatus(Enum):
    """Current status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REMOVED = "removed"


@dataclass
class Job:
    """
    Represents a scheduled job with all its metadata.
    
    Attributes:
        id: Unique identifier for the job
        func_name: Name of the function to execute (for logging)
        frequency: How often the job should run
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        next_run: Next scheduled execution time
        created_at: When the job was created
        status: Current job status
        last_run: Last execution time (if any)
        last_result: Result of last execution (if any)
        last_error: Error message from last execution (if any)
        run_count: Number of times job has executed
        max_runs: Maximum number of runs (None for unlimited)
    """
    id: str
    func_name: str
    frequency: Frequency
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    next_run: datetime = field(default_factory=datetime.now)
    created_at: datetime = field(default_factory=datetime.now)
    status: JobStatus = JobStatus.PENDING
    last_run: Optional[datetime] = None
    last_result: Optional[Any] = None
    last_error: Optional[str] = None
    run_count: int = 0
    max_runs: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for serialization."""
        data = asdict(self)
        data['frequency'] = self.frequency.value
        data['status'] = self.status.value
        data['next_run'] = self.next_run.isoformat()
        data['created_at'] = self.created_at.isoformat()
        if self.last_run:
            data['last_run'] = self.last_run.isoformat()
        else:
            data['last_run'] = None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create job from dictionary (deserialization)."""
        data = data.copy()
        data['frequency'] = Frequency(data['frequency'])
        data['status'] = JobStatus(data['status'])
        data['next_run'] = datetime.fromisoformat(data['next_run'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data['last_run']:
            data['last_run'] = datetime.fromisoformat(data['last_run'])
        data['args'] = tuple(data['args'])
        return cls(**data)


class TaskSchedulerError(Exception):
    """Base exception for task scheduler errors."""
    pass


class JobNotFoundError(TaskSchedulerError):
    """Raised when a job ID is not found."""
    pass


class InvalidFrequencyError(TaskSchedulerError):
    """Raised when an invalid frequency is provided."""
    pass


class PersistenceError(TaskSchedulerError):
    """Raised when persistence operations fail."""
    pass


class ValidationError(TaskSchedulerError):
    """Raised when input validation fails."""
    pass


def _validate_frequency(frequency: Union[Frequency, str]) -> Frequency:
    """
    Validate and convert frequency input to Frequency enum.
    
    Args:
        frequency: Frequency enum or string value
        
    Returns:
        Validated Frequency enum
        
    Raises:
        InvalidFrequencyError: If frequency is not valid
    """
    if isinstance(frequency, Frequency):
        return frequency
    if isinstance(frequency, str):
        try:
            return Frequency(frequency.lower())
        except ValueError:
            pass
    raise InvalidFrequencyError(
        f"Invalid frequency: {frequency}. "
        f"Must be one of: {[f.value for f in Frequency]}"
    )


def _validate_callable(func: Callable[..., Any]) -> None:
    """
    Validate that the provided object is callable.
    
    Args:
        func: Object to validate
        
    Raises:
        ValidationError: If func is not callable
    """
    if not callable(func):
        raise ValidationError(f"Provided function is not callable: {type(func)}")


def _validate_job_id(job_id: str) -> None:
    """
    Validate job ID format (UUID).
    
    Args:
        job_id: Job ID string to validate
        
    Raises:
        ValidationError: If job_id is not a valid UUID
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise ValidationError(f"Invalid job ID format: {job_id}")


def _calculate_next_run(frequency: Frequency, from_time: Optional[datetime] = None) -> datetime:
    """
    Calculate next run time based on frequency.
    
    Args:
        frequency: Job frequency
        from_time: Base time (defaults to now)
        
    Returns:
        Next scheduled run time
    """
    if from_time is None:
        from_time = datetime.now()
    
    if frequency == Frequency.MINUTE:
        # Next minute boundary
        return from_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
    elif frequency == Frequency.HOURLY:
        # Next hour boundary
        return from_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif frequency == Frequency.DAILY:
        # Next day at midnight
        return (from_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise InvalidFrequencyError(f"Unknown frequency: {frequency}")


class TaskScheduler:
    """
    Thread-safe task scheduler with persistence and logging.
    
    Manages scheduled jobs with support for different frequencies,
    automatic persistence to disk, and comprehensive execution logging.
    
    Attributes:
        persistence_file: Path to JSON file for job persistence
        logger: Configured logger instance
        
    Example:
        >>> scheduler = TaskScheduler("jobs.json")
        >>> job_id = scheduler.add_job(my_func, Frequency.HOURLY)
        >>> scheduler.start()
        >>> scheduler.remove_job(job_id)
        >>> scheduler.shutdown()
    """
    
    def __init__(
        self,
        persistence_file: Union[str, Path] = "scheduler_jobs.json",
        log_level: int = logging.INFO,
        log_file: Optional[Union[str, Path]] = None,
        max_workers: int = 10
    ) -> None:
        """
        Initialize the task scheduler.
        
        Args:
            persistence_file: Path to JSON file for job persistence
            log_level: Logging level (default: INFO)
            log_file: Optional log file path (default: stdout only)
            max_workers: Maximum concurrent job executions
            
        Raises:
            PersistenceError: If persistence file cannot be accessed
            ValidationError: If max_workers is not positive
        """
        if max_workers <= 0:
            raise ValidationError("max_workers must be positive")
        
        self._persistence_file = Path(persistence_file).resolve()
        self._max_workers = max_workers
        self._jobs: Dict[str, Job] = {}
        self._jobs_lock = threading.RLock()
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._worker_semaphore = threading.Semaphore(max_workers)
        self._shutdown_event = threading.Event()
        self._func_registry: Dict[str, Callable[..., Any]] = {}
        
        # Setup logging
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(log_level)
        self._logger.propagate = False
        
        # Clear existing handlers
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_format)
        self._logger.addHandler(console_handler)
        
        # File handler if specified
        if log_file:
            log_path = Path(log_file).resolve()
            # Security: prevent path traversal
            if not str(log_path).startswith(str(Path.cwd())):
                raise ValidationError("Log file must be within current working directory")
            file_handler = logging.FileHandler(log_path)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(console_format)
            self._logger.addHandler(file_handler)
        
        # Load persisted jobs
        self._load_jobs()
        
        # Register shutdown handlers
        atexit.register(self.shutdown)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self._logger.info(f"TaskScheduler initialized with persistence: {self._persistence_file}")
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        self._logger.info(f"Received signal {signum}, initiating shutdown")
        self.shutdown()
    
    def register_function(self, func: Callable[..., Any], name: Optional[str] = None) -> str:
        """
        Register a function for use in scheduled jobs.
        
        Functions must be registered before they can be used in jobs.
        This prevents arbitrary code execution from persisted job data.
        
        Args:
            func: Callable to register
            name: Optional name (defaults to func.__name__)
            
        Returns:
            Registered function name
            
        Raises:
            ValidationError: If func is not callable or name conflicts
        """
        _validate_callable(func)
        func_name = name or func.__qualname__
        
        with self._jobs_lock:
            if func_name in self._func_registry:
                if self._func_registry[func_name] is not func:
                    raise ValidationError(f"Function name already registered: {func_name}")
            self._func_registry[func_name] = func
        
        self._logger.debug(f"Registered function: {func_name}")
        return func_name
    
    def add_job(
        self,
        func: Callable[..., Any],
        frequency: Union[Frequency, str],
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        max_runs: Optional[int] = None,
        job_id: Optional[str] = None
    ) -> str:
        """
        Add a new scheduled job.
        
        Args:
            func: Callable to execute (must be registered)
            frequency: Execution frequency (MINUTE, HOURLY, DAILY)
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            start_time: When to first run (default: next frequency boundary)
            max_runs: Maximum executions (None for unlimited)
            job_id: Optional custom job ID (auto-generated if not provided)
            
        Returns:
            Job ID of the created job
            
        Raises:
            ValidationError: If inputs are invalid
            InvalidFrequencyError: If frequency is not supported
        """
        _validate_callable(func)
        freq = _validate_frequency(frequency)
        
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        
        if max_runs is not None and max_runs <= 0:
            raise ValidationError("max_runs must be positive or None")
        
        # Get or register function name
        func_name = func.__qualname__
        with self._jobs_lock:
            if func_name not in self._func_registry:
                self.register_function(func, func_name)
        
        # Generate job ID
        if job_id is None:
            job_id = str(uuid.uuid4())
        else:
            _validate_job_id(job_id)
            with self._jobs_lock:
                if job_id in self._jobs:
                    raise ValidationError(f"Job ID already exists: {job_id}")
        
        # Calculate next run time
        if start_time is None:
            next_run = _calculate_next_run(freq)
        else:
            if start_time < datetime.now():
                raise ValidationError("start_time cannot be in the past")
            next_run = start_time
        
        # Create job
        job = Job(
            id=job_id,
            func_name=func_name,
            frequency=freq,
            args=args,
            kwargs=kwargs,
            next_run=next_run,
            max_runs=max_runs
        )
        
        with self._jobs_lock:
            self._jobs[job_id] = job
        
        self._persist_jobs()
        self._logger.info(f"Added job {job_id}: {func_name} every {freq.value} starting at {next_run}")
        return job_id
    
    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.
        
        Args:
            job_id: ID of the job to remove
            
        Returns:
            True if job was found and removed, False otherwise
            
        Raises:
            ValidationError: If job_id format is invalid
        """
        _validate_job_id(job_id)
        
        with self._jobs_lock:
            if job_id not in self._jobs:
                self._logger.warning(f"Attempted to remove non-existent job: {job_id}")
                return False
            
            job = self._jobs[job_id]
            job.status = JobStatus.REMOVED
            del self._jobs[job_id]
        
        self._persist_jobs()
        self._logger.info(f"Removed job: {job_id}")
        return True
    
    def get_job(self, job_id: str) -> Job:
        """
        Get job details by ID.
        
        Args:
            job_id: ID of the job to retrieve
            
        Returns:
            Job object
            
        Raises:
            JobNotFoundError: If job_id not found
            ValidationError: If job_id format is invalid
        """
        _validate_job_id(job_id)
        
        with self._jobs_lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")
            return self._jobs[job_id]
    
    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        """
        List all jobs, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            List of Job objects
        """
        with self._jobs_lock:
            jobs = list(self._jobs.values())
        
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        
        return sorted(jobs, key=lambda j: j.next_run)
    
    def start(self) -> None:
        """
        Start the scheduler background thread.
        
        Raises:
            RuntimeError: If scheduler is already running
        """
        with self._jobs_lock:
            if self._running:
                raise RuntimeError("Scheduler is already running")
            self._running = True
            self._shutdown_event.clear()
        
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TaskScheduler",
            daemon=True
        )
        self._scheduler_thread.start()
        self._logger.info("Scheduler started")
    
    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """
        Stop the scheduler and wait for completion.
        
        Args:
            wait: Whether to wait for running jobs to complete
            timeout: Maximum time to wait for shutdown (seconds)
        """
        self._logger.info("Shutting down scheduler...")
        self._sh
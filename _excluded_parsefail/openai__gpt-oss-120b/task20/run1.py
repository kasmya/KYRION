"""
distributed_task_queue.py

A lightweight distributed task queue implementation using the Python standard
library and the widely‑used ``concurrent.futures`` package.  Tasks are stored
persistently in a SQLite database, can be enqueued from any process, and are
executed in parallel by a pool of worker processes.  The module tracks task
status, supports automatic retries on failure, and provides explicit error
handling.

Only the standard library is required; no external services (e.g. Redis) are
used, making the module self‑contained and suitable for many deployment
scenarios.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import threading
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Enums and Data structures
# --------------------------------------------------------------------------- #


class TaskState(str, Enum):
    """Possible states of a task in the queue."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


@dataclass
class Task:
    """Representation of a single task."""

    task_id: str
    func_path: str
    args_json: str
    kwargs_json: str
    retries_left: int
    state: TaskState
    result_json: Optional[str] = None
    error_json: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat()
    updated_at: str = datetime.utcnow().isoformat()


# --------------------------------------------------------------------------- #
# Helper functions for SQLite persistence
# --------------------------------------------------------------------------- #


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a SQLite connection with appropriate pragmas."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(db_path: Path) -> None:
    """Create the tasks table if it does not already exist."""
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                func_path TEXT NOT NULL,
                args_json TEXT NOT NULL,
                kwargs_json TEXT NOT NULL,
                retries_left INTEGER NOT NULL,
                state TEXT NOT NULL,
                result_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def _insert_task(conn: sqlite3.Connection, task: Task) -> None:
    """Insert a new task record."""
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, func_path, args_json, kwargs_json,
            retries_left, state, result_json, error_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            task.task_id,
            task.func_path,
            task.args_json,
            task.kwargs_json,
            task.retries_left,
            task.state,
            task.result_json,
            task.error_json,
            task.created_at,
            task.updated_at,
        ),
    )
    conn.commit()


def _update_task(conn: sqlite3.Connection, task_id: str, **updates: Any) -> None:
    """Update mutable fields of a task."""
    if not updates:
        return
    columns = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values())
    values.append(task_id)
    conn.execute(f"UPDATE tasks SET {columns} WHERE task_id=?;", values)
    conn.commit()


def _fetch_one_task(conn: sqlite3.Connection, task_id: str) -> Optional[Task]:
    """Retrieve a single task by its identifier."""
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?;", (task_id,)).fetchone()
    if row is None:
        return None
    return Task(**row)


def _fetch_next_pending(conn: sqlite3.Connection) -> Optional[Task]:
    """Atomically fetch the next pending task and mark it as RUNNING."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM tasks
        WHERE state IN (?, ?) AND retries_left >= 0
        ORDER BY created_at ASC
        LIMIT 1
        FOR UPDATE;
        """,
        (TaskState.PENDING.value, TaskState.RETRYING.value),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    task = Task(**row)
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        UPDATE tasks
        SET state=?, updated_at=?
        WHERE task_id=?;
        """,
        (TaskState.RUNNING.value, now, task.task_id),
    )
    conn.commit()
    return task


# --------------------------------------------------------------------------- #
# Core execution logic
# --------------------------------------------------------------------------- #


def _load_callable(func_path: str) -> Callable:
    """
    Import and return a callable given its full dotted path.

    Parameters
    ----------
    func_path: str
        Fully qualified name, e.g. ``my_pkg.module.my_func``.

    Returns
    -------
    Callable
        The imported callable.

    Raises
    ------
    ImportError
        If the module cannot be imported.
    AttributeError
        If the attribute does not exist in the module.
    TypeError
        If the resolved attribute is not callable.
    """
    module_name, _, attr = func_path.rpartition(".")
    if not module_name:
        raise ImportError(f"Invalid function path: '{func_path}'")
    module = importlib.import_module(module_name)
    callable_obj = getattr(module, attr)
    if not callable(callable_obj):
        raise TypeError(f"Resolved object '{func_path}' is not callable")
    return callable_obj


def _execute_task(task: Task) -> Tuple[TaskState, Optional[str], Optional[str]]:
    """
    Execute a task and return its new state, a JSON‑encoded result, and a JSON‑encoded error.

    Parameters
    ----------
    task: Task
        The task to execute.

    Returns
    -------
    Tuple[TaskState, Optional[str], Optional[str]]
        (new_state, result_json, error_json)
    """
    try:
        func = _load_callable(task.func_path)
        args = json.loads(task.args_json)
        kwargs = json.loads(task.kwargs_json)
        result = func(*args, **kwargs)
        result_json = json.dumps(result, default=str)
        return TaskState.SUCCESS, result_json, None
    except Exception as exc:  # pylint: disable=broad-except
        error_info = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        error_json = json.dumps(error_info)
        return TaskState.FAILED, None, error_json


# --------------------------------------------------------------------------- #
# Public API – DistributedTaskQueue
# --------------------------------------------------------------------------- #


class DistributedTaskQueue:
    """
    A simple distributed task queue with persistent storage, parallel workers,
    status tracking, and automatic retry on failure.

    Example
    -------
    >>> from distributed_task_queue import DistributedTaskQueue
    >>> q = DistributedTaskQueue(max_workers=4)
    >>> q.start()
    >>> task_id = q.enqueue(my_module.my_func, args=(1, 2), retries=2)
    >>> status = q.get_status(task_id)
    >>> q.stop()
    """

    def __init__(
        self,
        db_path: str | Path = "tasks.db",
        max_workers: int = 4,
        poll_interval: float = 0.5,
    ) -> None:
        """
        Initialise the queue.

        Parameters
        ----------
        db_path: str | Path
            File path for the SQLite database.
        max_workers: int
            Number of worker processes to spawn.
        poll_interval: float
            Seconds to wait between polling attempts for new tasks.
        """
        self.db_path = Path(db_path).expanduser().resolve()
        _init_db(self.db_path)

        self.max_workers = max_workers
        self.poll_interval = poll_interval

        self._executor: Optional[ProcessPoolExecutor] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------- #
    # Lifecycle management
    # ------------------------------------------------------------------- #

    def start(self) -> None:
        """
        Start the worker pool and the background monitor thread.

        Raises
        ------
        RuntimeError
            If the queue is already running.
        """
        if self._executor is not None:
            raise RuntimeError("Task queue is already started")
        self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="TaskQueueMonitor", daemon=True
        )
        self._monitor_thread.start()

    def stop(self, timeout: Optional[float] = None) -> None:
        """
        Stop the monitor thread and gracefully shut down the worker pool.

        Parameters
        ----------
        timeout: Optional[float]
            Maximum seconds to wait for workers to finish.  ``None`` means wait indefinitely.

        Raises
        ------
        RuntimeError
            If the queue is not running.
        """
        if self._executor is None:
            raise RuntimeError("Task queue is not started")
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=timeout)
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._executor = None
        self._monitor_thread = None

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def enqueue(
        self,
        func: Callable,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        retries: int = 0,
    ) -> str:
        """
        Enqueue a callable for asynchronous execution.

        Parameters
        ----------
        func: Callable
            The function to execute.  Must be importable via its dotted path.
        args: Tuple[Any, ...]
            Positional arguments for the function.
        kwargs: Optional[Dict[str, Any]]
            Keyword arguments for the function.
        retries: int
            Number of times to retry the task on failure.

        Returns
        -------
        str
            Unique identifier of the created task.

        Raises
        ------
        ValueError
            If ``retries`` is negative.
        TypeError
            If ``func`` cannot be resolved to an importable path.
        """
        if retries < 0:
            raise ValueError("retries must be non‑negative")
        if kwargs is None:
            kwargs = {}

        # Resolve function path safely
        if not hasattr(func, "__module__") or not hasattr(func, "__qualname__"):
            raise TypeError("Provided func is not a standard Python callable")
        func_path = f"{func.__module__}.{func.__qualname__}"

        task_id = uuid.uuid4().hex
        task = Task(
            task_id=task_id,
            func_path=func_path,
            args_json=json.dumps(args, default=str),
            kwargs_json=json.dumps(kwargs, default=str),
            retries_left=retries,
            state=TaskState.PENDING,
        )
        with _get_connection(self.db_path) as conn:
            _insert_task(conn, task)
        return task_id

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Retrieve the current status and metadata of a task.

        Parameters
        ----------
        task_id: str
            Identifier of the task.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing task fields.  Empty dict if task does not exist.
        """
        with _get_connection(self.db_path) as conn:
            task = _fetch_one_task(conn, task_id)
        if task is None:
            return {}
        result = asdict(task)
        # Convert JSON strings back to Python objects for convenience
        result["args"] = json.loads(task.args_json)
        result["kwargs"] = json.loads(task.kwargs_json)
        if task.result_json is not None:
            result["result"] = json.loads(task.result_json)
        else:
            result["result"] = None
        if task.error_json is not None:
            result["error"] = json.loads(task.error_json)
        else:
            result["error"] = None
        # Cleanup internal JSON fields
        del result["args_json"]
        del result["kwargs_json"]
        del result["result_json"]
        del result["error_json"]
        return result

    # ------------------------------------------------------------------- #
    # Internal monitoring loop
    # ------------------------------------------------------------------- #

    def _monitor_loop(self) -> None:
        """Continuously pull pending tasks and submit them to the executor."""
        while not self._stop_event.is_set():
            try:
                with _get_connection(self.db_path) as conn:
                    task = _fetch_next_pending(conn)
                if task is None:
                    self._stop_event.wait(self.poll_interval)
                    continue

                future = self._executor.submit(_execute_task, task)  # type: ignore[arg-type]
                with self._lock:
                    self._futures[task.task_id] = future
                future.add_done_callback(self._make_callback(task.task_id))
            except Exception:  # pylint: disable=broad-except
                # Log the unexpected error; for this self‑contained example we simply
                # print to stderr.  In production replace with proper logging.
                traceback.print_exc()
                self._stop_event.wait(self.poll_interval)

    def _make_callback(self, task_id: str) -> Callable[[Future], None]:
        """
        Create a callback that updates the task record based on execution outcome.

        Parameters
        ----------
        task_id: str
            Identifier of the task whose future we are handling.

        Returns
        -------
        Callable[[Future], None]
            Callback function.
        """

        def _callback(fut: Future) -> None:
            try:
                new_state, result_json, error_json = fut.result()
            except Exception:  # pylint: disable=broad-except
                # Unexpected failure inside the worker process
                new_state = TaskState.FAILED
                result_json = None
                error_json = json.dumps(
                    {
                        "type": "WorkerException",
                        "message": "Uncaught exception in worker",
                        "traceback": traceback.format_exc(),
                    }
                )
            with _get_connection(self.db_path) as conn:
                task = _fetch_one_task(conn, task_id)
                if task is None:
                    return  # Task was manually deleted; nothing to do
                update_fields: Dict[str, Any] = {
                    "state": new_state.value,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                if new_state == TaskState.SUCCESS:
                    update_fields["result_json"] = result_json
                    update_fields["retries_left"] = 0
                elif new_state == TaskState.FAILED:
                    update_fields["error_json"] = error_json
                    if task.retries_left > 0:
                        update_fields["retries_left"] = task.retries_left - 1
                        update_fields["state"] = TaskState.RETRYING.value
                    else:
                        update_fields["retries_left"] = 0
                else:  # RETRYING
                    update_fields["retries_left"] = task.retries_left - 1
                _update_task(conn, task_id, **update_fields)
            with self._lock:
                self._futures.pop(task_id, None)

        return _callback

    # ------------------------------------------------------------------- #
    # Utility methods (optional)
    # ------------------------------------------------------------------- #

    def list_tasks(self,
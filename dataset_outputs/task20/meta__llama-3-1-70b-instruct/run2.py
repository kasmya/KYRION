from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List
from concurrent.futures import ThreadPoolExecutor
import logging
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Task status
class TaskStatus(str, Enum):
    """Task status enum"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"

# Task dataclass
@dataclass
class Task:
    """Task dataclass"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    func: Callable
    args: List = field(default_factory=list)
    kwargs: Dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0

# Task queue
class TaskQueue:
    """Task queue"""
    def __init__(self, num_workers: int = 5):
        self.tasks: Dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

    def add_task(self, task: Task):
        """Add task to queue"""
        self.tasks[task.id] = task

    def process_tasks(self):
        """Process tasks in parallel"""
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.PENDING:
                self.executor.submit(self.run_task, task_id)

    def run_task(self, task_id: str):
        """Run task"""
        task = self.tasks[task_id]
        try:
            task.func(*task.args, **task.kwargs)
            task.status = TaskStatus.SUCCESS
        except Exception as e:
            task.status = TaskStatus.FAILURE
            task.retries += 1
            logger.error(f"Task {task_id} failed: {e}")
            if task.retries < 3:  # retry 3 times
                self.executor.submit(self.run_task, task_id)

    def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status"""
        return self.tasks[task_id].status

# Example usage
def add(a: int, b: int) -> int:
    """Example function"""
    return a + b

queue = TaskQueue()
task = Task(name="add_task", func=add, args=[2, 3])
queue.add_task(task)
queue.process_tasks()
logger.info(queue.get_task_status(task.id))  # TaskStatus.SUCCESS
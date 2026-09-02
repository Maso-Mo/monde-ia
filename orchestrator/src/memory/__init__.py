"""orchestrator.src.memory

SQLite, dataclasses et repository pour toutes les entites ZFLM.

Les composants :

- :class:`Database`            : wrapper sqlite3 + DDL idempotent
- :mod:`.models`               : DTOs (Project, Level, Task, Attempt, ...)
- :mod:`.repository`           : CRUD par entite
- :mod:`.schema`               : DDL SQL charge depuis schema.sql
"""

from .connection import Database
from .models import (
    Project,
    Level,
    Task,
    Attempt,
    LLMCall,
    Review,
    Validation,
    ErrorRecord,
    MemoryEntry,
    ProviderState,
    GitSnapshot,
)
from .repository import (
    ProjectRepository,
    LevelRepository,
    TaskRepository,
    AttemptRepository,
    LLMCallRepository,
    ReviewRepository,
    ValidationRepository,
    ErrorRepository,
    MemoryRepository,
    ProviderStateRepository,
    GitSnapshotRepository,
)

__all__ = [
    "Database",
    "Project",
    "Level",
    "Task",
    "Attempt",
    "LLMCall",
    "Review",
    "Validation",
    "ErrorRecord",
    "MemoryEntry",
    "ProviderState",
    "GitSnapshot",
    "ProjectRepository",
    "LevelRepository",
    "TaskRepository",
    "AttemptRepository",
    "LLMCallRepository",
    "ReviewRepository",
    "ValidationRepository",
    "ErrorRepository",
    "MemoryRepository",
    "ProviderStateRepository",
    "GitSnapshotRepository",
]

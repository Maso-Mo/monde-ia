"""
Recovery : retrouve l'etat courant de l'orchestrateur depuis SQLite.

Au demarrage, l'orchestrateur doit pouvoir :

1. Identifier le projet actif (status='active', le plus recent) ;
2. Identifier le niveau courant (current_level_id du projet) ;
3. Identifier la derniere tache creee sur ce niveau ;
4. Identifier la derniere tentative de cette tache ;
5. Reconnaitre son etat (``attempt.state``) pour reprendre.

Le retour est encapsule dans :class ``RecoverySnapshot``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..memory import (
    AttemptRepository,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)


@dataclass(slots=True)
class RecoverySnapshot:
    project_id: Optional[int]
    project_name: Optional[str]
    project_status: Optional[str]
    level_id: Optional[int]
    level_number: Optional[int]
    task_id: Optional[int]
    attempt_id: Optional[int]
    attempt_state: Optional[str]
    previous_state: Optional[str]

    @property
    def is_recoverable(self) -> bool:
        return self.attempt_id is not None and self.attempt_state is not None

    def summary(self) -> str:
        return (
            f"project={self.project_name} (id={self.project_id}, status={self.project_status}) "
            f"level={self.level_number} (id={self.level_id}) "
            f"task={self.task_id} attempt={self.attempt_id} state={self.attempt_state}"
        )


def find_active_state(
    projects: ProjectRepository,
    levels: LevelRepository,
    tasks: TaskRepository,
    attempts: AttemptRepository,
) -> RecoverySnapshot:
    """Parcourt les tables pour reconstituer l'etat courant."""
    # 1. Projet actif : preferer celui qui a current_level_id non nul.
    candidates = [p for p in projects.list_all() if p.status == "active"]
    project = None
    for p in candidates:
        if p.current_level_id is not None:
            project = p
            break
    if project is None and candidates:
        project = candidates[-1]

    if project is None:
        return RecoverySnapshot(None, None, None, None, None, None, None, None, None)

    # 2. Niveau courant.
    level = None
    if project.current_level_id is not None:
        level = levels.get(project.current_level_id)
    if level is None:
        all_levels = levels.list_for_project(project.id)
        if all_levels:
            level = all_levels[-1]
            # On force la mise a jour pour les futurs redemarrages.
            projects.set_current_level(project.id, level.id)

    # 3. Tache.
    task = None
    if level is not None:
        task_list = tasks.list_for_level(level.id)
        if task_list:
            task = task_list[-1]

    # 4. Tentative.
    attempt = None
    if task is not None:
        attempt_list = attempts.list_for_task(task.id)
        if attempt_list:
            attempt = attempt_list[-1]

    return RecoverySnapshot(
        project_id=project.id,
        project_name=project.name,
        project_status=project.status,
        level_id=level.id if level else None,
        level_number=level.level_number if level else None,
        task_id=task.id if task else None,
        attempt_id=attempt.id if attempt else None,
        attempt_state=attempt.state if attempt else None,
        previous_state=attempt.previous_state if attempt else None,
    )


def latest_attempt(
    attempts: AttemptRepository,
) -> Optional:
    """Renvoie la derniere tentative (toutes tasks confondues)."""
    return attempts.latest_active()


__all__ = ["RecoverySnapshot", "find_active_state", "latest_attempt"]

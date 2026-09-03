"""
Boucle de developpement : execute un cycle MOCK de A a Z.

Ce module :
- prend une DB deja initialisee et un provider mock ;
- cree un Project + Level + Task si besoin ;
- enchaine les transitions de la state machine ;
- appelle le provider mock pour chaque etape ;
- respecte la limite de 3 tentatives par Task ;
- emet des evenements via le logger.

C'est ce qu'on lance en mode ``--mock-cycle`` dans main.py.
"""

from __future__ import annotations

from typing import Optional

from src.llm.interfaces import LLMProvider
from src.memory import (
    AttemptRepository,
    Database,
    LevelRepository,
    ProjectRepository,
    TaskRepository,
)
from src.obs_logging.logger import JsonlLogger
from src.state_machine import (
    AttemptState,
    AttemptStateMachine,
    InvalidTransition,
)


class MockCycle:
    """Execute un cycle mock complet sur une tache."""

    def __init__(
        self,
        *,
        db: Database,
        provider: LLMProvider,
        logger: JsonlLogger,
        max_attempts: int = 3,
        roles_config: Optional[dict] = None,
    ):
        self._db = db
        self._provider = provider
        self._logger = logger
        self._max_attempts = max_attempts
        self._roles = roles_config or {}

        self._projects = ProjectRepository(db)
        self._levels = LevelRepository(db)
        self._tasks = TaskRepository(db)
        self._attempts = AttemptRepository(db)
        self._machine = AttemptStateMachine(
            db=db,
            logger=logger,
        )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def run_once(
        self,
        *,
        project_name: str = "demo-project",
        level_number: int = 1,
        task_description: str = "Demo task",
    ) -> int:
        """Execute un cycle complet. Renvoie l'id de la tache."""
        project = self._ensure_project(project_name)
        level = self._ensure_level(project.id, level_number)
        task = self._ensure_task(level.id, task_description)

        self._projects.set_current_level(project.id, level.id)
        self._logger.event(
            event="cycle.start",
            project_id=project.id,
            level_id=level.id,
            task_id=task.id,
        )

        attempt = self._next_attempt_for(task.id)

        while attempt is not None:
            self._drive_attempt(attempt)
            attempt = self._next_attempt_for(task.id)

        self._logger.event(
            event="cycle.end",
            project_id=project.id,
            level_id=level.id,
            task_id=task.id,
        )
        return task.id

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_project(self, name: str):
        for p in self._projects.list_all():
            if p.name == name:
                return p
        return self._projects.create(name)

    def _ensure_level(self, project_id: int, level_number: int):
        for lvl in self._levels.list_for_project(project_id):
            if lvl.level_number == level_number:
                return lvl
        return self._levels.create(
            project_id=project_id,
            level_number=level_number,
            spec=f"<level:{level_number}>",
        )

    def _ensure_task(self, level_id: int, description: str):
        existing = self._tasks.list_for_level(level_id)
        for t in existing:
            if t.description == description:
                return t
        return self._tasks.create(level_id=level_id, description=description)

    def _next_attempt_for(self, task_id: int):
        """Renvoie le prochain Attempt a traiter.

        Logique :

        - si un Attempt est encore non COMPLETED, on le reprend ;
        - sinon, on regarde le dernier Attempt :
            * status == 'failed' (FAILED_AFTER_RETRIES) -> stop ;
            * status == 'done' (APPROVED->COMPLETED)       -> stop ;
            * status == 'active' (RETRY_PENDING->COMPLETED)-> on en cree un nouveau si on n'a pas atteint max_attempts.
        """
        existing = self._attempts.list_for_task(task_id)
        for a in existing:
            if a.state != "COMPLETED":
                return a

        if not existing:
            return self._attempts.create(task_id=task_id, attempt_number=1)

        last = existing[-1]
        if last.status != "active":
            # 'done' ou 'failed' : on s'arrete.
            return None

        if len(existing) >= self._max_attempts:
            return None

        next_num = len(existing) + 1
        return self._attempts.create(
            task_id=task_id,
            attempt_number=next_num,
        )

    def _drive_attempt(self, attempt) -> None:
        """Chaine les transitions jusqu'a un etat terminal."""
        # On prend l'attempt comme objet memoire (mutable via la machine).
        try:
            self._machine.transition(attempt, AttemptState.PREPARING)
            self._machine.transition(attempt, AttemptState.GENERATING)
        except InvalidTransition as e:
            self._logger.error(
                event="cycle.transition_error",
                attempt_id=attempt.id,
                details={"error": str(e)},
            )
            return

        # Generation MOCK
        gen = self._provider.generate(
            prompt="<mock>",
            role_config=self._roles.get("generator", {}),
        )
        self._logger.event(
            event="cycle.generate",
            attempt_id=attempt.id,
            details={"tokens": gen.token_usage},
        )

        # BUILDING -> TESTING -> REVIEWING -> VALIDATING (chemin normal).
        try:
            self._machine.transition(attempt, AttemptState.BUILDING)
            self._machine.transition(attempt, AttemptState.TESTING)
            self._machine.transition(attempt, AttemptState.REVIEWING)

            review = self._provider.review(
                code=gen.text,
                role_config=self._roles.get("reviewer", {}),
            )
            self._logger.event(
                event="cycle.review",
                attempt_id=attempt.id,
                details={"issues": review.issues_found},
            )

            self._machine.transition(attempt, AttemptState.VALIDATING)

            validation = self._provider.validate(
                code=gen.text,
                role_config=self._roles.get("validator", {}),
            )
            self._logger.event(
                event="cycle.validate",
                attempt_id=attempt.id,
                details={"status": validation.status},
            )

            if validation.status == "approved":
                self._machine.transition(attempt, AttemptState.APPROVED)
                self._machine.transition(attempt, AttemptState.COMPLETED)
                self._attempts.update_status(attempt.id, "done")
            else:
                self._machine.transition(attempt, AttemptState.RETRY_PENDING)
                # L'Attempt courant est clos, le suivant sera cree par
                # _next_attempt_for si on n'a pas atteint max_attempts.
                # Si on a deja atteint max_attempts, c'est l'equivalent
                # de FAILED_AFTER_RETRIES -> COMPLETED, status='failed'.
                total = self._attempts.count_for_task(attempt.task_id)
                self._machine.transition(attempt, AttemptState.COMPLETED)
                if total >= self._max_attempts:
                    self._attempts.update_status(attempt.id, "failed")
                else:
                    self._attempts.update_status(attempt.id, "active")

        except InvalidTransition as e:
            self._logger.error(
                event="cycle.transition_error",
                attempt_id=attempt.id,
                details={"error": str(e)},
            )


__all__ = ["MockCycle"]

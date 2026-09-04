"""
RealCycle : boucle d'execution reelle avec FreeLLMAPIProvider.

Cette boucle :
- utilise FreeLLMAPIProvider pour les appels LLM reels ;
- catch FreeLLMAPIError et declenche PAUSED_PROVIDER si retryable ;
- met a jour ProviderState et enregistre les erreurs ;
- supporte la reprise automatique depuis PAUSED_PROVIDER ;
- respect strictement la state machine existante.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from src.llm import (
    FreeLLMAPIProvider,
    FreeLLMAPIError,
    create_freellmapi_provider,
    load_roles_config,
    GenerationResult,
    ReviewResult,
    ValidationResult,
    LLMProvider,
)
from src.memory import (
    AttemptRepository,
    Database,
    ErrorRepository,
    LevelRepository,
    LLMCallRepository,
    ProjectRepository,
    ProviderStateRepository,
    ReviewRepository,
    TaskRepository,
    ValidationRepository,
)
from src.obs_logging.logger import JsonlLogger
from src.state_machine import (
    AttemptState,
    AttemptStateMachine,
    InvalidTransition,
    StateMachineError,
)


# ----------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------

# Etats LLM qui peuvent entrer en PAUSED_PROVIDER
_LLM_STATES = {
    AttemptState.GENERATING,
    AttemptState.REVIEWING,
    AttemptState.VALIDATING,
}

# Codes d'erreur retryable (mappes depuis FreeLLMAPIProvider)
_RETRYABLE_ERROR_CODES = {
    "TIMEOUT",
    "NETWORK_ERROR",
    "RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
}


# ----------------------------------------------------------------------
# Resultat d'une etape LLM
# ----------------------------------------------------------------------


@dataclass(slots=True)
class LLMStepResult:
    """Resultat d'une etape LLM avec metadata pour logging."""
    success: bool
    result: Optional[object] = None
    error: Optional[FreeLLMAPIError] = None
    latency_ms: int = 0
    token_usage: Optional[int] = None


# ----------------------------------------------------------------------
# RealCycle
# ----------------------------------------------------------------------


class RealCycle:
    """Execute un cycle complet avec FreeLLMAPIProvider et gestion PAUSED_PROVIDER."""

    def __init__(
        self,
        *,
        db: Database,
        provider: Optional[LLMProvider] = None,
        logger: Optional[JsonlLogger] = None,
        max_attempts: int = 3,
        roles_config: Optional[dict] = None,
        auto_resume: bool = True,
    ):
        self._db = db
        self._logger = logger
        self._max_attempts = max_attempts
        self._roles = roles_config or {}
        self._auto_resume = auto_resume

        # Provider par defaut : FreeLLMAPIProvider depuis env
        if provider is None:
            provider = create_freellmapi_provider()
        self._provider = provider

        # Repositories
        self._projects = ProjectRepository(db)
        self._levels = LevelRepository(db)
        self._tasks = TaskRepository(db)
        self._attempts = AttemptRepository(db)
        self._llm_calls = LLMCallRepository(db)
        self._reviews = ReviewRepository(db)
        self._validations = ValidationRepository(db)
        self._errors = ErrorRepository(db)
        self._provider_states = ProviderStateRepository(db)

        # State machine
        self._machine = AttemptStateMachine(
            db=db,
            logger=logger,
        )

    # ------------------------------------------------------------------
    # API publique
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
        if self._logger:
            self._logger.event(
                event="cycle.start",
                project_id=project.id,
                level_id=level.id,
                task_id=task.id,
            )

        attempt = self._next_attempt_for(task.id)

        while attempt is not None:
            self._drive_attempt(attempt)
            # Recharge l'attempt depuis la DB (etat peut avoir change)
            attempt = self._attempts.get(attempt.id)
            if attempt and attempt.state != "COMPLETED":
                # Si on est en PAUSED_PROVIDER, essayer de reprendre
                if attempt.state == "PAUSED_PROVIDER" and self._auto_resume:
                    resumed = self._try_resume(attempt)
                    attempt = self._attempts.get(attempt.id)
                    if not resumed:
                        # Provider encore indisponible : arreter le cycle
                        # L'attempt reste en PAUSED_PROVIDER pour reprise ultérieure
                        break
                else:
                    break
            # Prochain attempt si le precedent est termine
            attempt = self._next_attempt_for(task.id)

        if self._logger:
            self._logger.event(
                event="cycle.end",
                project_id=project.id,
                level_id=level.id,
                task_id=task.id,
            )
        return task.id

    def _try_resume(self, attempt) -> bool:
        """Essaie de reprendre depuis PAUSED_PROVIDER si provider sain."""
        if attempt.state != "PAUSED_PROVIDER":
            return False

        # Verifier la sante du provider
        health = self._provider.health()
        provider_key = f"{health.provider}/{health.model}"

        if health.status == "up":
            # Provider sain -> sortir de PAUSED_PROVIDER
            if self._logger:
                self._logger.event(
                    event="provider.health_check",
                    attempt_id=attempt.id,
                    details={"provider": health.provider, "model": health.model, "status": "up"},
                )
            self._provider_states.upsert(
                provider=health.provider,
                model=health.model,
                status="up",
            )
            try:
                self._machine.exit_paused(attempt)
                return True
            except (InvalidTransition, StateMachineError) as e:
                if self._logger:
                    self._logger.error(
                        event="cycle.resume_failed",
                        attempt_id=attempt.id,
                        details={"error": str(e)},
                    )
                return False
        else:
            # Provider encore indisponible -> rester en PAUSED_PROVIDER
            if self._logger:
                self._logger.event(
                    event="provider.health_check",
                    attempt_id=attempt.id,
                    details={"provider": health.provider, "model": health.model, "status": "down"},
                )
            self._provider_states.upsert(
                provider=health.provider,
                model=health.model,
                status="down",
                retry_after=health.detail,
            )
            return False

    # ------------------------------------------------------------------
    # Internals - gestion des etapes LLM
    # ------------------------------------------------------------------

    def _drive_attempt(self, attempt) -> None:
        """Chaine les transitions jusqu'a un etat terminal."""
        try:
            self._machine.transition(attempt, AttemptState.PREPARING)
            self._machine.transition(attempt, AttemptState.GENERATING)
        except InvalidTransition as e:
            if self._logger:
                self._logger.error(
                    event="cycle.transition_error",
                    attempt_id=attempt.id,
                    details={"error": str(e)},
                )
            return

        # Generation
        gen_result = self._execute_llm_step(
            attempt=attempt,
            role="generator",
            state=AttemptState.GENERATING,
            prompt_fn=lambda: "<generation prompt>",
            call_fn=lambda p, rc: self._provider.generate(prompt=p, role_config=rc),
        )
        if not gen_result.success:
            return  # PAUSED_PROVIDER ou erreur definitive

        # Enregistrer le LLMCall
        self._record_llm_call(
            attempt_id=attempt.id,
            role="generator",
            result=gen_result,
        )

        # BUILDING -> TESTING
        try:
            self._machine.transition(attempt, AttemptState.BUILDING)
            self._machine.transition(attempt, AttemptState.TESTING)
        except InvalidTransition as e:
            if self._logger:
                self._logger.error(
                    event="cycle.transition_error",
                    attempt_id=attempt.id,
                    details={"error": str(e)},
                )
            return

        # REVIEWING
        self._machine.transition(attempt, AttemptState.REVIEWING)
        review_result = self._execute_llm_step(
            attempt=attempt,
            role="reviewer",
            state=AttemptState.REVIEWING,
            prompt_fn=lambda: gen_result.result.text if gen_result.result else "",
            call_fn=lambda c, rc: self._provider.review(code=c, role_config=rc),
        )
        if not review_result.success:
            return

        self._record_llm_call(
            attempt_id=attempt.id,
            role="reviewer",
            result=review_result,
        )

        # Enregistrer la review
        if isinstance(review_result.result, ReviewResult):
            self._reviews.create(
                attempt_id=attempt.id,
                issues_found=review_result.result.issues_found,
                instructions_for_fix="\n".join(review_result.result.instructions_for_fix),
            )

        # VALIDATING
        self._machine.transition(attempt, AttemptState.VALIDATING)
        validation_result = self._execute_llm_step(
            attempt=attempt,
            role="validator",
            state=AttemptState.VALIDATING,
            prompt_fn=lambda: gen_result.result.text if gen_result.result else "",
            call_fn=lambda c, rc: self._provider.validate(code=c, role_config=rc),
        )
        if not validation_result.success:
            return

        self._record_llm_call(
            attempt_id=attempt.id,
            role="validator",
            result=validation_result,
        )

        # Enregistrer la validation
        if isinstance(validation_result.result, ValidationResult):
            self._validations.create(
                attempt_id=attempt.id,
                status=validation_result.result.status,
                score=validation_result.result.score,
                reason=validation_result.result.reason,
                blocking_issues=validation_result.result.blocking_issues,
            )

        # Verifier le verdict
        if isinstance(validation_result.result, ValidationResult) and validation_result.result.approved:
            self._machine.transition(attempt, AttemptState.APPROVED)
            self._machine.transition(attempt, AttemptState.COMPLETED)
            self._attempts.update_status(attempt.id, "done")
        else:
            self._machine.transition(attempt, AttemptState.RETRY_PENDING)
            total = self._attempts.count_for_task(attempt.task_id)
            self._machine.transition(attempt, AttemptState.COMPLETED)
            if total >= self._max_attempts:
                self._attempts.update_status(attempt.id, "failed")
            else:
                self._attempts.update_status(attempt.id, "active")

    def _execute_llm_step(
        self,
        *,
        attempt,
        role: str,
        state: AttemptState,
        prompt_fn,
        call_fn,
    ) -> LLMStepResult:
        """Execute une etape LLM avec gestion d'erreur et PAUSED_PROVIDER."""
        prompt = prompt_fn()
        role_config = self._roles.get(role, {})
        provider_name = role_config.get("provider", "unknown")
        model = role_config.get("model", "unknown")

        start = time.perf_counter()
        try:
            result = call_fn(prompt, role_config)
            latency_ms = int((time.perf_counter() - start) * 1000)

            # Succes - mettre a jour ProviderState
            self._provider_states.upsert(
                provider=provider_name,
                model=model,
                status="up",
            )

            return LLMStepResult(
                success=True,
                result=result,
                latency_ms=latency_ms,
                token_usage=getattr(result, "token_usage", None),
            )

        except FreeLLMAPIError as e:
            latency_ms = int((time.perf_counter() - start) * 1000)

            # Enregistrer l'erreur
            self._errors.create(
                attempt_id=attempt.id,
                type=e.code,
                message=str(e),
                raw_output_ref=None,
            )

            # Enregistrer le LLMCall en echec
            self._llm_calls.create(
                attempt_id=attempt.id,
                role=role,
                provider=provider_name,
                model=model,
                latency_ms=latency_ms,
                token_usage=None,
                prompt_ref=prompt[:500] if prompt else None,
                response_ref=str(e),
            )

            # Mettre a jour ProviderState - schema n'autorise que up/down/unknown
            status = "down"
            self._provider_states.upsert(
                provider=provider_name,
                model=model,
                status=status,
                retry_after=str(e.status_code) if e.status_code else None,
            )

            # Si erreur retryable et etat LLM -> PAUSED_PROVIDER
            if e.retryable and state in _LLM_STATES:
                if self._logger:
                    self._logger.event(
                        event="provider.error_retryable",
                        attempt_id=attempt.id,
                        details={"role": role, "error_code": e.code, "message": str(e)},
                    )
                try:
                    self._machine.enter_paused(attempt, reason=f"{role}: {e.code}")
                except (InvalidTransition, StateMachineError) as sm_err:
                    if self._logger:
                        self._logger.error(
                            event="cycle.enter_paused_failed",
                            attempt_id=attempt.id,
                            details={"error": str(sm_err)},
                        )
                return LLMStepResult(
                    success=False,
                    error=e,
                    latency_ms=latency_ms,
                )

            # Erreur non-retryable -> log et arret
            if self._logger:
                self._logger.error(
                    event="provider.error_fatal",
                    attempt_id=attempt.id,
                    details={"role": role, "error_code": e.code, "message": str(e)},
                )
            return LLMStepResult(
                success=False,
                error=e,
                latency_ms=latency_ms,
            )

    def _record_llm_call(
        self,
        *,
        attempt_id: int,
        role: str,
        result: LLMStepResult,
    ) -> None:
        """Enregistre un appel LLM reussi."""
        role_config = self._roles.get(role, {})
        self._llm_calls.create(
            attempt_id=attempt_id,
            role=role,
            provider=role_config.get("provider"),
            model=role_config.get("model"),
            latency_ms=result.latency_ms,
            token_usage=result.token_usage,
        )

    # ------------------------------------------------------------------
    # Helpers - creation entites
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
        """Renvoie le prochain Attempt a traiter."""
        existing = self._attempts.list_for_task(task_id)
        for a in existing:
            if a.state != "COMPLETED":
                return a

        if not existing:
            return self._attempts.create(task_id=task_id, attempt_number=1)

        last = existing[-1]
        if last.status != "active":
            return None

        if len(existing) >= self._max_attempts:
            return None

        next_num = len(existing) + 1
        return self._attempts.create(
            task_id=task_id,
            attempt_number=next_num,
        )


__all__ = ["RealCycle", "LLMStepResult"]
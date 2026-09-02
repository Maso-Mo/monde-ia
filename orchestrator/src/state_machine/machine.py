"""
Machine a etats persistante pour un Attempt ZFLM.

Responsabilites :
1. Encapsuler la transition courante (AttemptState source / cible).
2. Verifier la validite via ``transitions.is_allowed``.
3. Calculer les cas speciaux (PAUSED_PROVIDER).
4. Deleguer la persistance a ``AttemptRepository``.
5. Logger chaque transition via :mod:`obs_logging`.

L'orchestrateur ne doit JAMAIS modifier l'etat d'un Attempt directement
en SQL ; il passe par :class:`AttemptStateMachine`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from .states import AttemptState
from .transitions import is_allowed


class InvalidTransition(RuntimeError):
    """Levee quand une transition n'est pas autorisee."""


class StateMachineError(RuntimeError):
    """Erreur generique de la machine a etats."""


class AttemptLike(Protocol):
    """Tout ce qu'on attend d'un Attempt pour le piloter."""
    id: Optional[int]
    state: str
    previous_state: Optional[str]
    finished_at: Optional[str]


class AttemptWriter(Protocol):
    """Interface minimale de persistance d'un Attempt."""
    def update_state(
        self, attempt_id: int, *, state: str,
        previous_state: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None: ...


class TransitionLogger(Protocol):
    """Logger obs_logging (JsonlLogger-compatible)."""
    def event(self, *, event: str, **kwargs) -> None: ...


@dataclass(slots=True)
class TransitionResult:
    """Resultat d'une transition."""
    attempt_id: int
    from_state: str
    to_state: str
    previous_state: Optional[str] = None
    finished: bool = False


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttemptStateMachine:
    """Pilote la transition d'etat d'un Attempt."""

    def __init__(
        self,
        *,
        writer: AttemptWriter,
        logger: Optional[TransitionLogger] = None,
        now: Optional[Callable[[], str]] = None,
    ):
        self._writer = writer
        self._logger = logger
        self._now = now or _utcnow_iso

    def transition(
        self,
        attempt: AttemptLike,
        target: AttemptState,
    ) -> TransitionResult:
        """Effectue ``attempt.state -> target``."""
        if attempt.id is None:
            raise StateMachineError(
                "Cannot transition an Attempt that has not been persisted."
            )

        src = AttemptState(attempt.state)

        # Cas special : sortie de PAUSED_PROVIDER.
        if src == AttemptState.PAUSED_PROVIDER and target != AttemptState.PAUSED_PROVIDER:
            return self.exit_paused(attempt, target)

        if not is_allowed(src, target):
            raise InvalidTransition(
                f"Transition interdite : {src.value} -> {target.value}"
            )

        return self._apply(attempt, target, previous_state=None)

    def enter_paused(
        self,
        attempt: AttemptLike,
        reason: Optional[str] = None,
    ) -> TransitionResult:
        """Bascule l'Attempt dans PAUSED_PROVIDER en memorisant l'etat source."""
        if attempt.id is None:
            raise StateMachineError("Attempt not persisted.")

        src = AttemptState(attempt.state)
        target = AttemptState.PAUSED_PROVIDER

        if not is_allowed(src, target):
            raise InvalidTransition(
                f"Impossible d'entrer en PAUSED_PROVIDER depuis {src.value}"
            )

        result = self._apply(attempt, target, previous_state=src.value)

        if self._logger is not None:
            self._logger.event(
                event="state.paused_provider",
                attempt_id=attempt.id,
                state=target.value,
                details={"reason": reason} if reason else None,
            )
        return result

    def exit_paused(
        self,
        attempt: AttemptLike,
        target: Optional[AttemptState] = None,
    ) -> TransitionResult:
        """Sort de PAUSED_PROVIDER vers ``previous_state`` par defaut."""
        if attempt.id is None:
            raise StateMachineError("Attempt not persisted.")

        src = AttemptState(attempt.state)
        if src != AttemptState.PAUSED_PROVIDER:
            raise StateMachineError(
                f"exit_paused appele alors que l'etat est {src.value}"
            )

        previous = attempt.previous_state
        if previous is None:
            raise StateMachineError(
                "previous_state est NULL ; impossible de reprendre."
            )
        previous_state = AttemptState(previous)
        chosen = target or previous_state

        # Cas particulier : reprise sur l'etat identique (self-loop).
        # Une reprise "a l'identique" doit toujours etre permise, sinon
        # on ne pourrait jamais sortir de PAUSED_PROVIDER si le dernier
        # etat etait par exemple GENERATING.
        if previous_state == chosen:
            return self._apply(attempt, chosen, previous_state=None)

        if not is_allowed(previous_state, chosen):
            raise InvalidTransition(
                f"Reprise impossible : {previous_state.value} -> {chosen.value}"
            )

        result = self._apply(attempt, chosen, previous_state=None)

        if self._logger is not None:
            self._logger.event(
                event="state.resumed",
                attempt_id=attempt.id,
                state=chosen.value,
                details={"from_paused": True},
            )
        return result

    def _apply(
        self,
        attempt: AttemptLike,
        target: AttemptState,
        *,
        previous_state: Optional[str],
    ) -> TransitionResult:
        finished = target == AttemptState.COMPLETED
        finished_at = self._now() if finished else None

        self._writer.update_state(
            attempt.id,
            state=target.value,
            previous_state=previous_state,
            finished_at=finished_at,
        )

        result = TransitionResult(
            attempt_id=attempt.id,
            from_state=attempt.state,
            to_state=target.value,
            previous_state=previous_state,
            finished=finished,
        )

        if self._logger is not None:
            self._logger.event(
                event="state.transition",
                attempt_id=attempt.id,
                state=target.value,
                details={
                    "from": result.from_state,
                    "to": result.to_state,
                    "finished": finished,
                },
            )

        attempt.state = target.value
        attempt.previous_state = previous_state
        attempt.finished_at = finished_at

        return result


__all__ = [
    "AttemptStateMachine",
    "InvalidTransition",
    "StateMachineError",
    "TransitionResult",
    "AttemptLike",
    "AttemptWriter",
    "TransitionLogger",
]

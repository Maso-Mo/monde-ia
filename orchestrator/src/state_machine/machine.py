"""
Machine a etats persistante pour un Attempt ZFLM.

Responsabilites :

1. Encapsuler la transition courante (AttemptState source / cible).
2. Verifier la validite via ``transitions.is_allowed``.
3. Calculer les cas speciaux (PAUSED_PROVIDER).
4. Realiser une transition ATOMIQUE en SQLite :
   - UPDATE attempts.state (+ previous_state + finished_at)
   - INSERT INTO state_transitions (journal append-only)
   Les deux operations sont dans une SEULE transaction ; si l'une
   echoue, rien n'est persiste.
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


class StateMachineDB(Protocol):
    """Interface minimale de la base pour la machine a etats.

    L'implementation de production est :class:`src.memory.Database`
    qui fournit :meth:`record_state_transition` (operation atomique
    cross-table).
    """
    def record_state_transition(
        self,
        *,
        attempt_id: int,
        from_state: Optional[str],
        to_state: str,
        previous_state_field: Optional[str],
        finished_at: Optional[str],
        reason: Optional[str] = None,
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
    reason: Optional[str] = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttemptStateMachine:
    """Pilote la transition d'etat d'un Attempt."""

    def __init__(
        self,
        *,
        db: StateMachineDB,
        logger: Optional[TransitionLogger] = None,
        now: Optional[Callable[[], str]] = None,
    ):
        self._db = db
        self._logger = logger
        self._now = now or _utcnow_iso

    def transition(
        self,
        attempt: AttemptLike,
        target: AttemptState,
        *,
        reason: Optional[str] = None,
    ) -> TransitionResult:
        """Effectue ``attempt.state -> target``.

        Refuse toute transition non listee dans la table de transitions.
        La sortie de ``PAUSED_PROVIDER`` doit passer par
        :meth:`exit_paused`.
        """
        if attempt.id is None:
            raise StateMachineError(
                "Cannot transition an Attempt that has not been persisted."
            )

        src = AttemptState(attempt.state)
        if not is_allowed(src, target):
            raise InvalidTransition(
                f"Transition interdite : {src.value} -> {target.value}"
            )

        return self._apply(attempt, target, previous_state=None, reason=reason)

    def enter_paused(
        self,
        attempt: AttemptLike,
        reason: Optional[str] = None,
    ) -> TransitionResult:
        """Bascule l'Attempt dans PAUSED_PROVIDER en memorisant l'etat source.

        Appele typiquement quand un provider LLM est indisponible.
        Seuls ``GENERATING``, ``REVIEWING`` et ``VALIDATING`` peuvent
        entrer en PAUSED_PROVIDER.
        """
        if attempt.id is None:
            raise StateMachineError("Attempt not persisted.")

        src = AttemptState(attempt.state)
        target = AttemptState.PAUSED_PROVIDER

        if not is_allowed(src, target):
            raise InvalidTransition(
                f"Impossible d'entrer en PAUSED_PROVIDER depuis {src.value}"
            )

        result = self._apply(
            attempt,
            target,
            previous_state=src.value,
            reason=reason,
        )

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
    ) -> TransitionResult:
        """Sort de PAUSED_PROVIDER vers ``previous_state`` (forcement).

        Aucune cible arbitraire n'est acceptee : la sortie est strictement
        limitee a l'etat memorise dans ``previous_state``.
        """
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

        chosen = AttemptState(previous)

        result = self._apply(
            attempt,
            chosen,
            previous_state=None,
            reason="resume_after_pause",
        )

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
        reason: Optional[str],
    ) -> TransitionResult:
        finished = target == AttemptState.COMPLETED
        finished_at = self._now() if finished else None

        # Operation ATOMIQUE : UPDATE attempts + INSERT state_transitions
        # dans la meme transaction SQLite.
        self._db.record_state_transition(
            attempt_id=attempt.id,
            from_state=attempt.state,
            to_state=target.value,
            previous_state_field=previous_state,
            finished_at=finished_at,
            reason=reason,
        )

        result = TransitionResult(
            attempt_id=attempt.id,
            from_state=attempt.state,
            to_state=target.value,
            previous_state=previous_state,
            finished=finished,
            reason=reason,
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
                    "reason": reason,
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
    "StateMachineDB",
    "TransitionLogger",
]

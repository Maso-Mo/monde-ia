"""
Table des transitions autorisées pour la machine à états d'un Attempt.

Convention :

- Une transition est représentée par ``(from, to)`` ;
- ``is_allowed(from, to)`` retourne True si la transition est valide ;
- Toute transition non listée est INTERDITE et lèvera
  ``InvalidTransition`` si elle est tentée via ``StateMachine``.

Règles implémentées :

- CREATED -> PREPARING
- PREPARING -> GENERATING
- GENERATING -> BUILDING, RETRY_PENDING
- BUILDING -> TESTING, RETRY_PENDING
- TESTING -> REVIEWING, RETRY_PENDING
- REVIEWING -> VALIDATING
- VALIDATING -> APPROVED, RETRY_PENDING
- APPROVED -> COMPLETED
- RETRY_PENDING -> COMPLETED  (utilisé après spawn d'un nouvel Attempt)
- FAILED_AFTER_RETRIES -> COMPLETED
- PAUSED_PROVIDER -> PAUSED_PROVIDER->previous_state géré hors table

Le passage vers PAUSED_PROVIDER est géré via :func:`enter_paused` car il
nécessite la mémorisation de l'état précédent.
"""

from __future__ import annotations

from .states import AttemptState


# ----------------------------------------------------------------------
# Table des transitions
# ----------------------------------------------------------------------

_ALLOWED: dict[AttemptState, frozenset[AttemptState]] = {
    AttemptState.CREATED: frozenset({
        AttemptState.PREPARING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.PREPARING: frozenset({
        AttemptState.GENERATING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.GENERATING: frozenset({
        AttemptState.BUILDING,
        AttemptState.RETRY_PENDING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.BUILDING: frozenset({
        AttemptState.TESTING,
        AttemptState.RETRY_PENDING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.TESTING: frozenset({
        AttemptState.REVIEWING,
        AttemptState.RETRY_PENDING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.REVIEWING: frozenset({
        AttemptState.VALIDATING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.VALIDATING: frozenset({
        AttemptState.APPROVED,
        AttemptState.RETRY_PENDING,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.APPROVED: frozenset({
        AttemptState.COMPLETED,
    }),
    AttemptState.RETRY_PENDING: frozenset({
        AttemptState.COMPLETED,  # l'Attempt courant est clos
        AttemptState.FAILED_AFTER_RETRIES,
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.FAILED_AFTER_RETRIES: frozenset({
        AttemptState.COMPLETED,
    }),
    AttemptState.PAUSED_PROVIDER: frozenset({
        # La sortie vers previous_state est gérée par :func:`exit_paused`.
        # On autorise aussi les autres transitions naturelles depuis
        # PAUSED_PROVIDER si l'orchestrateur le décide.
        AttemptState.PAUSED_PROVIDER,
    }),
    AttemptState.COMPLETED: frozenset(),
}


def is_allowed(src: AttemptState, dst: AttemptState) -> bool:
    """Retourne True si ``src -> dst`` est une transition valide."""
    return dst in _ALLOWED.get(src, frozenset())


def allowed_targets(src: AttemptState) -> frozenset[AttemptState]:
    """Liste (immuable) des transitions autorisées depuis ``src``."""
    return _ALLOWED.get(src, frozenset())


__all__ = ["is_allowed", "allowed_targets"]
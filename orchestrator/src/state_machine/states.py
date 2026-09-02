"""
États d'un Attempt ZFLM.

L'enum est ``str``-mixin pour pouvoir être stockée directement en TEXT
dans SQLite. Les valeurs sont en MAJUSCULES (cf. schéma SQL et spec).
"""

from __future__ import annotations

from enum import Enum


class AttemptState(str, Enum):
    """Tous les états possibles d'un Attempt."""

    CREATED = "CREATED"
    PREPARING = "PREPARING"
    GENERATING = "GENERATING"
    BUILDING = "BUILDING"
    TESTING = "TESTING"
    REVIEWING = "REVIEWING"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED_AFTER_RETRIES = "FAILED_AFTER_RETRIES"
    PAUSED_PROVIDER = "PAUSED_PROVIDER"
    COMPLETED = "COMPLETED"


# ----------------------------------------------------------------------
# Catégories
# ----------------------------------------------------------------------

# États terminaux : aucune transition autorisée.
TERMINAL_STATES: frozenset[AttemptState] = frozenset({
    AttemptState.COMPLETED,
})

# États intermédiaires "actifs" où l'Attempt est en cours de traitement.
ACTIVE_STATES: frozenset[AttemptState] = frozenset({
    AttemptState.PREPARING,
    AttemptState.GENERATING,
    AttemptState.BUILDING,
    AttemptState.TESTING,
    AttemptState.REVIEWING,
    AttemptState.VALIDATING,
})

# États "résultats" : signés comme fin d'un cycle mais peuvent encore
# transiter (APPROVED -> COMPLETED, FAILED_AFTER_RETRIES -> COMPLETED).
RESULT_STATES: frozenset[AttemptState] = frozenset({
    AttemptState.APPROVED,
    AttemptState.FAILED_AFTER_RETRIES,
})


__all__ = ["AttemptState", "TERMINAL_STATES", "ACTIVE_STATES", "RESULT_STATES"]
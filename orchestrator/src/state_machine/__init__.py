"""orchestrator.src.state_machine

Machine a etats persistante pour un Attempt.

Voir :

- :mod:`.states` pour l'enum ``AttemptState``
- :mod:`.transitions` pour la table de transitions
- :mod:`.machine` pour la classe :class:`AttemptStateMachine`
"""

from .states import (
    AttemptState,
    TERMINAL_STATES,
    ACTIVE_STATES,
    RESULT_STATES,
)
from .transitions import is_allowed, allowed_targets
from .machine import (
    AttemptStateMachine,
    InvalidTransition,
    StateMachineError,
    TransitionResult,
)

__all__ = [
    "AttemptState",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
    "RESULT_STATES",
    "is_allowed",
    "allowed_targets",
    "AttemptStateMachine",
    "InvalidTransition",
    "StateMachineError",
    "TransitionResult",
]

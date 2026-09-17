"""aside-jev: bounded TypeSafe Jev decisions for Aside agents."""

__version__ = "0.1.0"

from .core import Candidate, Outcome, build_abstain, classify, validate_choice
from .jev import choose_live, choose_mock

__all__ = [
    "Candidate",
    "Outcome",
    "build_abstain",
    "classify",
    "validate_choice",
    "choose_live",
    "choose_mock",
    "__version__",
]

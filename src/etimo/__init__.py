"""etimo — recursive reconstruction of a word's formal history.

Given a word, the tool walks from ancestor to ancestor until the chain reaches
a terminal: a reconstructed root, a declared uncertain origin, or the
exhaustion of the available data.
"""

from .cache import DiskCache
from .models import Form, Hypothesis, Node, Relation, Step, Terminal
from .version import __version__
from .walker import Reconstructor, Result
from .wiktionary import (
    DictSource,
    SessionMemory,
    SourceError,
    WikitextSource,
    WiktionaryClient,
)

__all__ = [
    "DictSource",
    "DiskCache",
    "Form",
    "Hypothesis",
    "Node",
    "Reconstructor",
    "Relation",
    "Result",
    "SessionMemory",
    "SourceError",
    "Step",
    "Terminal",
    "WikitextSource",
    "WiktionaryClient",
    "__version__",
]

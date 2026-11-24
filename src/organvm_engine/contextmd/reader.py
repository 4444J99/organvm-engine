"""Read the generated system context for a directory.

The full generated text lives in ``docs/organvm-context.md``; the instruction
files (CLAUDE.md, GEMINI.md, AGENTS.md) carry only a pointer to it. A directory
that has not been synced since the generator changed still holds the full text
inline between the AUTO markers, so readers go to the document first and fall
back to such a legacy in-file block.
"""

from __future__ import annotations

import re
from pathlib import Path

from organvm_engine.contextmd import (
    AUTO_END,
    AUTO_START,
    CONTEXT_DOCUMENT_RELPATH,
    INSTRUCTION_FILENAMES,
)

# The pointer's first line is its fingerprint: a legacy full block never
# carries it, and an identity pointer carries it along with the repo's
# identity lines, so a word cap can no longer tell them apart.
_POINTER_SENTENCE = (
    "Generated system context (organ, edges, directives, task queue, density) is in"
)
_BLOCK_PATTERN = re.compile(re.escape(AUTO_START) + r"(.*?)" + re.escape(AUTO_END), re.DOTALL)


def is_pointer_block(block: str) -> bool:
    """Return whether an AUTO block is the pointer rather than generated text."""
    return CONTEXT_DOCUMENT_RELPATH in block and _POINTER_SENTENCE in block


def read_generated_context(directory: Path | str) -> str | None:
    """Return the generated context for ``directory``, or None if it has none.

    Reads ``<directory>/docs/organvm-context.md`` first. Otherwise falls back to
    the first legacy full block found in CLAUDE.md, AGENTS.md or GEMINI.md (a
    pointer-only block is not content and is skipped).
    """
    root = Path(directory)
    document = root / CONTEXT_DOCUMENT_RELPATH
    if document.is_file():
        return document.read_text(encoding="utf-8")
    for filename in INSTRUCTION_FILENAMES:
        path = root / filename
        if not path.is_file():
            continue
        match = _BLOCK_PATTERN.search(path.read_text(encoding="utf-8"))
        if match and not is_pointer_block(match.group(1)):
            return match.group(1).strip("\n")
    return None

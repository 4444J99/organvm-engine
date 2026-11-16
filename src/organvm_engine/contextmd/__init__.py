"""System context file auto-generator.

Generates and injects system context sections into CLAUDE.md, GEMINI.md,
and AGENTS.md files across the ORGANVM workspace. Keeps the AI context
layer synchronized with registry-v2.json and seed.yaml contracts.

Auto-generated sections are demarcated:
    <!-- ORGANVM:AUTO:START -->
    ## System Context (auto-generated)
    ...
    <!-- ORGANVM:AUTO:END -->

Anything outside these markers is preserved untouched.

The generated text itself lives in one shared, generator-owned file per
directory (``docs/organvm-context.md``). The instruction files only carry a
short pointer to it between the markers, so agents that auto-load them do not
carry the generated text into every session.
"""

# Marker constants used by generator and sync
AUTO_START = "<!-- ORGANVM:AUTO:START -->"
AUTO_END = "<!-- ORGANVM:AUTO:END -->"

# Shared, generator-owned context file (relative to each target directory) and
# the instruction files that point to it.
CONTEXT_DOCUMENT_RELPATH = "docs/organvm-context.md"
INSTRUCTION_FILENAMES = ("CLAUDE.md", "GEMINI.md", "AGENTS.md")

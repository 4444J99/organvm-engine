# Contributing to organvm-engine

Thank you for your interest in contributing to this project.

## Overview

Organvm Engine is the system engine for the organvm meta-org. It provides registry validation, metrics calculation, and system-level tooling that operates across all eight organs. It reads from registry-v2.json and coordinates cross-org operations.

**Stack:** Python (system engine, registry validation, metrics)

## Prerequisites

- Git
- Python 3.11+
- A GitHub account

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/organvm-engine.git
cd organvm-engine

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

The full suite needs two packages a bare checkout does not have: the private
`organvm-ontologia` dependency (CI pins a commit in `.github/workflows/ci.yml`;
install it from a checkout of that commit) and the `dev` extra
(`pip install -e ".[dev]"`, which provides `nbformat`). Without them the
ontologia bridge tests and the reader-mode audit tests fail at import, not on
behavior.

The suite is host-independent: `tests/conftest.py` clears `ORGANVM_*` /
`LIMEN_GOV_*` environment variables and the host's global git config and ignore
file for every test. A test that needs an override sets it with
`monkeypatch.setenv`.

## How to Contribute

### Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Use the provided issue templates when available
- Include clear reproduction steps for bugs
- For documentation issues, specify which file and section

### Making Changes

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Create a branch** for your change:
   ```bash
   git checkout -b feat/your-feature-name
   ```
4. **Make your changes** following the code style guidelines below
5. **Test** your changes:
   ```bash
   pytest -v
   ```
6. **Commit** with a clear, imperative-mood message:
   ```bash
   git commit -m "add validation for edge case in parser"
   ```
7. **Push** your branch and open a Pull Request

### Code Style

Follow PEP 8. Use type hints. Prefer f-strings for formatting. Scripts should use argparse for CLI interfaces and print clear status messages. Handle API errors gracefully.

### Commit Messages

- Use imperative mood: "add feature" not "added feature"
- Keep the title under 72 characters
- Reference issue numbers when applicable: "fix auth bug (#42)"
- Keep commits atomic and focused on a single change

## Pull Request Process

1. Fill out the PR template with a description of your changes
2. Reference any related issues
3. Ensure all CI checks pass
4. Request review from a maintainer
5. Address review feedback promptly

PRs should be focused — one feature or fix per PR. Large changes should be
discussed in an issue first.

## Code of Conduct

Be respectful, constructive, and honest. This project is part of the
[organvm system](https://github.com/meta-organvm), which values transparency
and building in public. We follow the
[Contributor Covenant](https://www.contributor-covenant.org/).

## Questions?

Open an issue on this repository or start a discussion if discussions are
enabled. For system-wide questions, see
[orchestration-start-here](https://github.com/organvm-iv-taxis/orchestration-start-here).

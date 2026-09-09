"""Small fail-closed primitives for bounded filesystem discovery reads."""

from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_DISCOVERY_INPUT_BYTES = 16_000_000


class StableReadError(RuntimeError):
    """Raised when a discovery input cannot be read as one stable regular file."""


class StableReadSizeLimitError(StableReadError):
    """A regular input exceeded the declared byte limit before or during reading."""


def read_stable_regular_bytes(
    path: Path | str,
    *,
    maximum_bytes: int = MAX_DISCOVERY_INPUT_BYTES,
) -> bytes:
    """Read one bounded regular file without following path components.

    ``O_NONBLOCK`` prevents a regular-to-FIFO race from hanging discovery.
    Descriptor, pathname, and lexical-parent identities are rebound after the
    read so callers never consume a mixed or detached filesystem snapshot.
    """
    candidate = Path(path).expanduser()
    if maximum_bytes < 0:
        raise ValueError("maximum_bytes must be non-negative")
    parent_fd: int | None = None
    live_parent_fd: int | None = None
    descriptor: int | None = None
    try:
        parent_fd, filename = _open_parent_no_follow(candidate)
        initial = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise StableReadError(f"discovery input is not a regular file: {candidate}")
        if initial.st_size > maximum_bytes:
            raise StableReadSizeLimitError(f"discovery input exceeds size limit: {candidate}")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (
            initial.st_dev,
            initial.st_ino,
        ):
            raise StableReadError(f"discovery input changed before open: {candidate}")

        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 128 * 1024):
            total += len(chunk)
            if total > maximum_bytes:
                raise StableReadSizeLimitError(f"discovery input exceeds size limit: {candidate}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        live_parent_fd, live_filename = _open_parent_no_follow(candidate)
        opened_parent = os.fstat(parent_fd)
        live_parent = os.fstat(live_parent_fd)
        live_current = os.stat(
            live_filename,
            dir_fd=live_parent_fd,
            follow_symlinks=False,
        )
    except StableReadError:
        raise
    except OSError as exc:
        raise StableReadError(f"cannot bind discovery input {candidate}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if live_parent_fd is not None:
            os.close(live_parent_fd)
        if parent_fd is not None:
            os.close(parent_fd)

    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        total != before.st_size
        or live_filename != filename
        or (opened_parent.st_dev, opened_parent.st_ino)
        != (live_parent.st_dev, live_parent.st_ino)
        or any(
            getattr(before, field) != getattr(after, field)
            or getattr(before, field) != getattr(current, field)
            or getattr(before, field) != getattr(live_current, field)
            for field in stable_fields
        )
    ):
        raise StableReadError(f"discovery input changed while reading: {candidate}")
    return b"".join(chunks)


def _open_parent_no_follow(path: Path) -> tuple[int, str]:
    """Open an absolute lexical parent one real directory at a time."""
    absolute = Path(os.path.normpath(str(path.absolute())))
    if not absolute.name:
        raise StableReadError(f"discovery input path has no filename: {path}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(absolute.anchor or os.sep, flags)
    try:
        parts = absolute.parts[1:] if absolute.anchor else absolute.parts
        for component in parts[:-1]:
            child_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
    except Exception:
        os.close(parent_fd)
        raise
    return parent_fd, absolute.name

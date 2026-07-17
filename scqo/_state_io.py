"""Shared on-disk plumbing for the two per-context state stores.

Both stores — :mod:`scqo.config`'s ``scqo_state.json`` and :mod:`scqo.physical`'s
``physical.json`` — keep the CURRENT values in a small human-readable JSON and the
full change history in a sidecar, one ChangeRecord JSON object per line::

    scqo_state.json   + scqo_state.history.jsonl
    physical.json     + physical.history.jsonl

The sidecar is *logically* append-only (rows are only ever added, never rewritten)
but physically maintained by lock-guarded read-merge-rewrite via a unique temp +
``os.replace``: a save must read the full history anyway (to merge a co-running
same-context session's rows), atomic replace means no torn half-lines on Windows,
and a true ``O_APPEND`` would duplicate rows when a partially-failed save is
retried. Row order in the file is by timestamp (the :func:`scqo.config._now`
fixed-offset guarantee), which provenance's last-record-wins rule depends on.

``read_history`` falls back to the pre-split layout where the values file itself
held a ``"history"`` list (dev machines that ran main's WIP before the split);
the next save writes the sidecar and drops the embedded key.

The lock file (``<values file>.lock``, moved here from :mod:`scqo.physical`)
guards a whole values+history save so two same-context sessions cannot erase
each other's rows.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

#: Lock acquisition gives up after this many seconds (another writer is stuck).
_LOCK_TIMEOUT_S = 10.0
#: A lock file older than this is a crashed writer's leftover and is taken over.
_LOCK_STALE_S = 10.0


@contextmanager
def _file_lock(target: Path):
    """`O_CREAT|O_EXCL` lock file next to ``target`` — cross-platform, no deps.

    Retries for :data:`_LOCK_TIMEOUT_S`; a lock older than :data:`_LOCK_STALE_S`
    is a crashed writer's leftover. State saves are rare and take milliseconds,
    so contention is the exception, not the rule — but the file is shared by
    every same-context session, so two subtle races are closed:

    * **Stale takeover is atomic.** Two waiters must not both "break" one stale
      lock and then both enter the section. The stale lock is claimed by
      ``os.replace``-renaming it to a per-waiter unique name: exactly one waiter's
      rename succeeds (the OS guarantees it), the losers' raise and simply retry.
    * **A lock is only ever released by its owner.** Each acquisition writes a
      unique token into the lock file; release unlinks ONLY if the token still
      matches. So if our lock were ever deemed stale and taken over while we
      paused, we do not delete the new holder's lock out from under it.
    """
    lock = target.with_name(target.name + ".lock")
    token = f"{os.getpid()}.{os.urandom(6).hex()}".encode()
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, token)
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > _LOCK_STALE_S
            except OSError:
                stale = False  # raced with the holder's release — just retry
            if stale:
                # Atomic claim: only ONE waiter's rename of the stale lock can
                # succeed; the winner removes it and retries the O_EXCL create,
                # the losers' os.replace raises (already gone) and they retry too.
                claim = lock.with_name(f"{lock.name}.stale.{os.getpid()}.{os.urandom(4).hex()}")
                try:
                    os.replace(lock, claim)
                    claim.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"could not lock {target} within {_LOCK_TIMEOUT_S:.0f}s — if no other "
                    f"scqo process is saving state, delete the stale {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if lock.read_bytes() == token:  # still OURS — never free a takeover's lock
                lock.unlink(missing_ok=True)
        except OSError:
            pass


def history_path(values_path: str | Path) -> Path:
    """The history sidecar of a values file (``scqo_state.json`` ->
    ``scqo_state.history.jsonl``)."""
    return Path(values_path).with_suffix(".history.jsonl")


def read_history(values_path: str | Path) -> list[dict]:
    """Every ChangeRecord dict belonging to a values file — sidecar first.

    When the sidecar exists it wins (an unparseable line — a torn hand edit, a
    copy truncation — is skipped with a warning rather than taking the whole
    store down). Otherwise the pre-split fallback reads the ``"history"`` list
    embedded in the values file itself; the next save splits it out.

    Lock-free readers (the viewer; store constructors) can interleave with
    another process's FIRST post-split save — sidecar created, then the values
    file's embedded key stripped. Writers create the sidecar first and never
    delete it, so "values file without the key" implies the sidecar exists: one
    re-check closes the window instead of returning an empty history that never
    existed on disk.
    """
    values_path = Path(values_path)
    sidecar = history_path(values_path)
    for attempt in (0, 1):
        if sidecar.is_file():
            records: list[dict] = []
            for lineno, line in enumerate(
                    sidecar.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"warning: {sidecar}:{lineno}: unparseable history line skipped",
                          file=sys.stderr)
            return records
        try:
            data = json.loads(values_path.read_text(encoding="utf-8"))
        except OSError:
            return []  # neither file: an empty (or reset) store
        if "history" in data or attempt:
            return list(data.get("history", []))
        # values file present but already stripped: a concurrent first split just
        # ran — the sidecar must exist now, so look again.
    return []  # pragma: no cover - unreachable (the loop always returns)


def write_history(values_path: str | Path, records: list[dict]) -> None:
    """Atomically rewrite the history sidecar (one compact JSON object per line).

    Unique temp + ``os.replace`` so a reader never sees a torn file; on failure
    the temp is removed and the previous sidecar (if any) is left untouched.
    """
    sidecar = history_path(values_path)
    tmp = sidecar.with_name(f"{sidecar.name}.{os.getpid()}.tmp")
    payload = "".join(json.dumps(r) + "\n" for r in records)
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

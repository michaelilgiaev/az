#!/usr/bin/env python3
"""Az'arch application menu -- launch-frequency usage tracking.

The menu lists applications ordered by how often the user opens them (most-used
first), exactly like Plasma's Kickoff "Frequently Used" behaviour. This module
owns that little bit of state: a JSON map of ``desktop_id -> launch count``
persisted under the XDG data dir, plus the ordering key used to sort the app
list.

Design:
  * Pure standard library. The store is a single small JSON file
    (``~/.local/share/azarch-application-menu/usage.json``).
  * Best-effort and crash-proof: a missing/corrupt/unreadable store simply reads
    back as "no usage yet" and the list falls back to alphabetical. A failed
    write never propagates -- launching an app must never fail because the
    counter could not be bumped.
  * Ordering: most-launched first; ties (including all never-launched apps,
    which share count 0) break alphabetically by display name, case-folded. So
    used apps float to the top in usage order and everything else stays in a
    stable A->Z tail.

Keyed by ``desktop_id`` (the .desktop basename, e.g. ``org.kde.dolphin.desktop``)
rather than the display name, so a renamed app keeps its history and two apps
that happen to share a name never collide.
"""

from __future__ import annotations

import json
import os
import tempfile


def _data_home() -> str:
    return os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )


# Overridable via the environment so tests can point it at a temp dir without
# touching the real user store.
def _store_path() -> str:
    override = os.environ.get("AZARCH_USAGE_FILE")
    if override:
        return override
    return os.path.join(
        _data_home(), "azarch-application-menu", "usage.json"
    )


class UsageStore:
    """Load / bump / persist per-app launch counts.

    Loaded once at construction (cheap: one small JSON read). ``record()`` bumps
    a counter in memory and writes the whole map back atomically. ``count()``
    and :meth:`order_key` are used by the menu to sort its rows.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or _store_path()
        self._counts: dict[str, int] = self._load()

    # -- persistence -------------------------------------------------------
    def _load(self) -> dict[str, int]:
        """Read the store, returning {} on any problem (missing/corrupt)."""
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, int] = {}
        for key, val in raw.items():
            # Be defensive: coerce sane ints, drop anything odd.
            try:
                n = int(val)
            except (TypeError, ValueError):
                continue
            if isinstance(key, str) and n > 0:
                out[key] = n
        return out

    def _save(self) -> None:
        """Write the whole map atomically (temp file + rename). Best-effort:
        any failure is swallowed so a launch is never blocked by disk state."""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix=".usage-", suffix=".json",
                dir=os.path.dirname(self.path),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self._counts, fh, separators=(",", ":"))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            finally:
                # If the rename already consumed tmp this is a harmless no-op.
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        except OSError:
            pass

    # -- queries / mutation ------------------------------------------------
    def count(self, desktop_id: str) -> int:
        """Launch count for a desktop id (0 if never launched)."""
        return self._counts.get(desktop_id, 0)

    def record(self, desktop_id: str) -> None:
        """Increment the launch counter for a desktop id and persist."""
        if not desktop_id:
            return
        self._counts[desktop_id] = self._counts.get(desktop_id, 0) + 1
        self._save()

    def order_key(self, entry) -> tuple[int, str]:
        """Sort key for an AppEntry: most-launched first, then A->Z by name.

        Python sorts ascending, so we negate the count to put the biggest count
        first, and pair it with the case-folded name so ties (all never-launched
        apps share -0) fall back to a stable alphabetical order.
        """
        return (-self.count(entry.desktop_id), entry.name.casefold())

    def sorted_apps(self, apps: list) -> list:
        """Return ``apps`` ordered by launch frequency (see :meth:`order_key`)."""
        return sorted(apps, key=self.order_key)


if __name__ == "__main__":
    # Tiny CLI: dump the current usage store.
    store = UsageStore()
    if not store._counts:
        print(f"(no usage recorded yet at {store.path})")
    for did, n in sorted(store._counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{n:5}  {did}")

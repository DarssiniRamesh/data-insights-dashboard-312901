"""
Compatibility helpers for running the backend in different import modes.

Why this exists
---------------
This repo commonly runs with:
  - PYTHONPATH=src and `uvicorn api.main:app` (preferred), where modules like
    `database`, `services`, `schemas`, `utils` are importable as top-level names.

Some environments/tools may instead import:
  - `uvicorn src.api.main:app` (package import), where code under `src/` is
    reachable as the `src.*` package.

Problem
-------
If the app is imported as `src.api.main`, then modules may be imported under both
namespaces (e.g., `src.database` and `database`), producing *two separate module
singletons*. This can cause subtle runtime issues like:
  - DB initialization happening on one module instance,
  - request handlers using the other module instance,
  - missing seeded rows (e.g., `system` user) and FK failures.

Solution
--------
When `src` is imported as a package, we alias common top-level module names to
their `src.*` equivalents via `sys.modules`. This keeps the application state
(singletons, caches) consistent regardless of import path.

Note: We intentionally do NOT execute any DB operations here.
"""
from __future__ import annotations

import importlib
import sys
from typing import Final

# Common subpackages that are imported throughout the codebase using top-level names.
_ALIAS_PACKAGES: Final[list[str]] = ["api", "database", "services", "schemas", "utils"]

for pkg in _ALIAS_PACKAGES:
    try:
        module = importlib.import_module(f"{__name__}.{pkg}")
        # Ensure `import database` (etc.) returns the same module object as `import src.database`.
        sys.modules.setdefault(pkg, module)
    except Exception:
        # Defensive: do not block app import if aliasing fails for any reason.
        # Import errors will still surface naturally when the missing module is used.
        continue

"""azarch ISO build system.

The whole build lives here as Python. `azarch.build` is the entrypoint
(invoked by the thin ``compile.sh`` shim after it sets up the PTY + sudo).

Design: every artifact baked into the ISO is authored as a Python string in
``azarch.configuration.*`` and written into the archiso profile tree by
``azarch.steps``. Only genuinely-large verbatim upstream files and the
user-facing package list live as data files under ``libraries/data/``.
"""

__all__ = ["build"]

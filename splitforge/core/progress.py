# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/progress.py
"""Progress feedback for long operations: cursor progress + status bar text.

``Progress`` keeps only plain numbers and text; the window manager and the
workspace are looked up from ``bpy.context`` on every call, so an instance may
live across modal events. In background mode the UI calls are skipped, but
``listeners`` (callables ``fn(done, total, text)``) are always called; tests use
them to count the steps.
"""

import bpy

listeners = []


def _wm():
    return getattr(bpy.context, "window_manager", None)


def _status(text):
    workspace = getattr(bpy.context, "workspace", None)
    if workspace is not None and not bpy.app.background:
        try:
            workspace.status_text_set(text)
        except (AttributeError, RuntimeError, ReferenceError):
            pass


class Progress:
    """``total`` steps; ``step(text)`` marks one more as started."""

    def __init__(self, total, label):
        self.total = max(1, int(total))
        self.done = 0
        self.label = label
        self.text = ""
        self.active = False

    def begin(self):
        wm = _wm()
        if wm is not None and not bpy.app.background:
            wm.progress_begin(0, self.total)
        self.active = True
        self._notify()

    def set_total(self, total):
        """Change the step count (once later steps are known)."""
        self.total = max(self.done, int(total), 1)
        wm = _wm()
        if self.active and wm is not None and not bpy.app.background:
            wm.progress_end()
            wm.progress_begin(0, self.total)
            wm.progress_update(self.done)

    def step(self, text):
        self.done += 1
        self.text = text
        wm = _wm()
        if self.active and wm is not None and not bpy.app.background:
            wm.progress_update(min(self.done, self.total))
        self._notify()

    def _notify(self):
        _status(f"{self.label}: {self.text} ({self.done}/{self.total})" if self.text else self.label)
        for fn in list(listeners):
            fn(self.done, self.total, self.text)

    def end(self):
        if not self.active:
            return
        self.active = False
        wm = _wm()
        if wm is not None and not bpy.app.background:
            wm.progress_end()
        _status(None)

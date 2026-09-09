"""Writing skin files safely, and cleaning up after ourselves.

Two hazards drove every decision here, both found by reading the Hermes source
rather than by guessing.

HAZARD 1 — THE TORN-READ LATCH
`tui_gateway/change_watcher.py:_broadcast_skin_if_changed` records the file's new
mtime signature BEFORE it parses the YAML:

    sig = _skin_sig()
    if sig == _last_skin_sig: return
    _last_skin_sig = sig            # <-- accepted here
    _broadcast_global_event("skin.changed", resolve_skin())   # <-- parsed here

and `skin_engine._load_skin_from_yaml` swallows a parse failure and returns None,
whereupon `load_skin` silently falls back to the DEFAULT skin. So if the watcher
stats a half-written file, it accepts that mtime, renders the default palette, and
— if our completed write lands on the same mtime — stays wrong until something
unrelated changes. A partial write is not a cosmetic glitch here; it LATCHES.

Therefore: never write the live file in place. Write a sibling temp file, fsync it,
validate the complete bytes, then atomically rename. os.replace is atomic on POSIX
and on Windows, so a reader sees either the old file or the new one, never a
fragment.

HAZARD 2 — SPARSE FORKS DO NOT INHERIT WHAT YOU THINK
`skin_engine._build_skin_config` merges a skin's `colors` block over the BUILT-IN
DEFAULT, not over some other skin. Skin-to-skin inheritance does not exist. A sparse
per-session file therefore inherits Hermes' default gold palette, not our dialect,
and looks broken in a way that is genuinely hard to diagnose. So every file we write
is fully MATERIALIZED: base dialect resolved first, our deltas applied on top, every
key present.

Also: the YAML's internal `name:` field is authoritative for identity and for
`list_skins()` discovery, so each per-session file carries its own unique name.
Duplicate internal names collapse into one entry in the picker.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .pattern import Palette

__all__ = [
    "skins_dir",
    "session_skin_name",
    "write_skin",
    "remove_skin",
    "sweep_orphans",
    "BASE_DIALECT",
    "write_colors",
]


# The chronic base. Sepia's own palette: leucophore warm white, chromatophore
# sepia/umber inks, iridophore teals and golds. These are the keys that do NOT
# vary per session — the dialect every session speaks.
#
# `background` is NOT here: it is per-session (the session's own near-black), so it
# comes from `Palette.skin_colors()` rather than from the shared dialect.
BASE_DIALECT: Mapping[str, str] = {
    "ui_text": "#E8E2D6",
    "banner_text": "#E8E2D6",
    "ui_primary": "#F2ECE0",
    "ui_label": "#D8CFC0",
    "banner_dim": "#6B6257",
    "ui_thinking": "#8A7F70",
    "ui_ok": "#5FB58A",
    "ui_warn": "#E0A448",
    "ui_error": "#D2544F",
    "syntax_string": "#7FB89A",
    "syntax_number": "#D9A05B",
    "syntax_keyword": "#C58FD0",
    "syntax_comment": "#6B6257",
}

_PREFIX = "cuttle-"


def skins_dir(hermes_home: str | os.PathLike[str] | None = None) -> Path:
    """The skins directory for the ACTIVE Hermes home.

    Honours $HERMES_HOME because profiles set it before imports; hardcoding
    ~/.hermes would silently write into the wrong profile.
    """
    if hermes_home is not None:
        root = Path(hermes_home)
    else:
        root = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return root / "skins"


def stable_skin_name() -> str:
    """The ONE skin name `display.skin` points at, for the life of the install.

    Session-scoped names cannot work for the ACTIVE skin: `init_skin_from_config`
    resolves `display.skin` at CLI startup, before any session exists, so a name
    containing a session id resolves to nothing and the CLI silently falls back to
    the stock `default` palette. That is precisely the bug that made the theme
    invisible. See bootstrap.py for the full account.
    """
    from .bootstrap import STABLE_SKIN

    return STABLE_SKIN


def session_skin_name(session_id: str) -> str:
    """Skin name for a session. Prefixed so `sweep_orphans` can identify what we own
    and, crucially, never delete a skin the user wrote by hand."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in session_id)
    return f"{_PREFIX}{safe}"


def _yaml_quote(value: str) -> str:
    """Quote a scalar for YAML.

    Hand-rolled rather than importing PyYAML: this module writes a tiny, fully
    known document (identifiers and #rrggbb strings), and a plugin that works
    without pulling a dependency into the agent's process is a better citizen.
    Anything unexpected is rejected outright rather than escaped creatively.
    """
    if any(c in value for c in '\n\r\t"\\'):
        raise ValueError(f"refusing to serialise unexpected scalar: {value!r}")
    return f'"{value}"'


def _render_yaml(name: str, colors: Mapping[str, str], description: str) -> str:
    lines = [
        f"name: {_yaml_quote(name)}",
        f"description: {_yaml_quote(description)}",
        "colors:",
    ]
    for key in sorted(colors):
        lines.append(f"  {key}: {_yaml_quote(colors[key])}")
    return "\n".join(lines) + "\n"


def write_skin(
    palette: Palette,
    *,
    hermes_home: str | os.PathLike[str] | None = None,
    extra: Mapping[str, Any] | None = None,
    tint_background: bool = True,
    durable: bool = True,
    name: str | None = None,
) -> Path:
    """Materialise *palette* into its session skin file, atomically.

    Returns the path written. The file is complete and valid at every instant an
    outside reader could observe it — see HAZARD 1 above.
    """
    colors = dict(BASE_DIALECT)
    colors.update(palette.skin_colors(tint_background=tint_background))
    if extra:
        colors.update({k: str(v) for k, v in extra.items()})
    return write_colors(
        palette.session_id,
        colors,
        description=f"cuttlefish session {palette.session_id} ({palette.signal.value})",
        hermes_home=hermes_home,
        durable=durable,
        name=name,
    )


def write_colors(
    session_id: str,
    colors: Mapping[str, str],
    *,
    description: str = "",
    hermes_home: str | os.PathLike[str] | None = None,
    durable: bool = True,
    name: str | None = None,
) -> Path:
    """Atomically write a raw colour mapping as this session's skin.

    The animation path needs this: an in-flight transition frame is an arbitrary
    interpolated palette, not a `Palette` dataclass.

    ``durable=False`` skips the fsync. That is safe and deliberate for intermediate
    animation frames: **atomicity comes from os.replace, not from fsync**, so a
    concurrent reader still sees either the whole old file or the whole new one and
    HAZARD 1 is unaffected. fsync only buys crash *durability*, and the durable
    thing to survive a crash is the final frame — which is always written with
    ``durable=True``. Measured on this box the fsync costs ~4ms of an ~11.7ms
    frame, so dropping it for in-flight frames is a third of the animation budget.
    """
    name = name or session_skin_name(session_id)
    directory = skins_dir(hermes_home)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}.yaml"

    body = _render_yaml(name, colors, description or f"cuttlefish session {session_id}")

    # Same directory as the target: os.replace is only atomic within a filesystem,
    # and /tmp is frequently a different one.
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            if durable:
                # fsync before rename: without it a crash can leave the rename
                # durable while the contents are not, producing an empty file —
                # which parses to None and latches the default skin.
                os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        # Never leave a stray temp file behind, including on KeyboardInterrupt.
        with_suppress_unlink(tmp_path)
        raise
    return target


def with_suppress_unlink(path: str | os.PathLike[str]) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def remove_skin(
    session_id: str, *, hermes_home: str | os.PathLike[str] | None = None
) -> bool:
    """Delete one session's skin file. True if a file was removed."""
    target = skins_dir(hermes_home) / f"{session_skin_name(session_id)}.yaml"
    if not target.is_file():
        return False
    # Refuse symlinks: deleting one would follow it out of our directory.
    if target.is_symlink():
        return False
    target.unlink()
    return True


def sweep_orphans(
    live_session_ids: set[str], *, hermes_home: str | os.PathLike[str] | None = None
) -> list[Path]:
    """Delete our skin files whose sessions are gone. Returns what was removed.

    This is the crash-recovery path: `kill -9` skips session-end cleanup, so
    something must reclaim those files later. Scoped to the `cuttle-` prefix and to
    regular files so a hand-written skin is never at risk.
    """
    directory = skins_dir(hermes_home)
    if not directory.is_dir():
        return []

    # The stable skin is what `display.skin` resolves at startup; reclaiming it
    # would leave the next CLI launch with nothing to load and it would fall back
    # to stock gold — the original bug, reintroduced by the cleanup path.
    keep = {session_skin_name(s) for s in live_session_ids} | {stable_skin_name()}
    removed: list[Path] = []
    for path in directory.glob(f"{_PREFIX}*.yaml"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.stem in keep:
            continue
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            # Another process may have swept it already; that is success, not failure.
            continue
    return removed

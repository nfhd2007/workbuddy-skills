#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One place that answers "where do skill packages live on this machine".

Why this module exists: preflight.py only *looks* (does quark-drive exist? is a
cookie file present?) while quark_share_download.py actually *reads* the cookie
to call the API. When the two resolve the skills root differently, one of them
says "logged in, ready" while the other 401s -- and worse, the preflight verdict
(`api` vs `gui`) is what decides whether the agent is allowed to touch the
network at all. Two copies of the resolution order drift apart, so there is
exactly one copy, here, and both scripts import it.

Resolution order, highest priority first:

  1. explicit *extra* roots from the caller -- normally the skills root this
     very skill was loaded from (``<skill_dir>/..``), because a host may mount
     skills under a per-workspace ``.skills`` directory instead of the default.
  2. ``QSI_SKILLS_DIR``           (set by bootstrap.sh/.ps1, or by the user)
  3. ``$WORKBUDDY_CONFIG_DIR/skills``  (defaults to ``~/.workbuddy/skills``)
  4. ``~/.workbuddy/skills``      (historical default, always tried last)

This module is read-only: it never creates, moves or deletes anything.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Relative location of the quark-drive cookie file inside a skills root.
COOKIE_RELPATH = ("quark-drive", "scripts", "cookie.txt")

#: Marker that proves a directory is a skill package of the given name.
SKILL_MARKER = "SKILL.md"


def workbuddy_config_dir():
    """The host config dir (``~/.workbuddy`` unless overridden)."""
    v = os.environ.get("WORKBUDDY_CONFIG_DIR", "").strip()
    if v:
        try:
            return Path(v).expanduser()
        except Exception:
            pass
    return Path.home() / ".workbuddy"


def _dedupe(paths):
    """Case-insensitive de-dup that preserves order (Windows paths differ in case)."""
    seen, out = set(), []
    for p in paths:
        try:
            key = str(p).rstrip("\\/").lower()
        except Exception:
            continue
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def skills_roots(extra=()):
    """Candidate skills roots, de-duplicated, highest priority first."""
    roots = []
    for raw in extra:
        if not raw:
            continue
        try:
            roots.append(Path(raw).expanduser())
        except Exception:
            pass
    qsi = os.environ.get("QSI_SKILLS_DIR", "").strip()
    if qsi:
        try:
            roots.append(Path(qsi).expanduser())
        except Exception:
            pass
    try:
        roots.append(workbuddy_config_dir() / "skills")
    except Exception:
        pass
    try:
        roots.append(Path.home() / ".workbuddy" / "skills")
    except Exception:
        pass
    return _dedupe(roots)


def local_skills_root(skill_dir):
    """The root this very skill was loaded from, or None if it is not a root.

    A host may mount skills under a per-workspace ``.skills`` directory, so the
    directory next to this skill package outranks the env/default roots. Only
    accept a parent actually named skills/.skills -- a checkout at
    ``D:/src/mytool/scripts/...`` is not a skills root and must not be treated
    as one.
    """
    try:
        parent = Path(skill_dir).resolve().parent
    except Exception:
        return None
    try:
        if parent.name.lower() in ("skills", ".skills"):
            return parent
    except Exception:
        pass
    return None


def install_skills_root(skill_dir):
    """Where a new skill package should be *written*.

    Write side, so the order differs from :func:`skills_roots` on purpose:

      1. ``QSI_SKILLS_DIR`` -- already resolved by the bootstrap layer
      2. the root this skill was loaded from (hosts may use ``.skills``)
      3. ``<config>/skills``

    ``~/.workbuddy/skills`` is deliberately not appended here: if the host
    actually reads a workspace ``.skills`` directory, writing to the default
    root would install a skill nothing ever loads -- and preflight would then
    report a root that does not match what the user sees.
    """
    qsi = os.environ.get("QSI_SKILLS_DIR", "").strip()
    if qsi:
        try:
            return Path(qsi).expanduser()
        except Exception:
            pass
    local = local_skills_root(skill_dir)
    if local:
        return local
    return workbuddy_config_dir() / "skills"


def cookie_candidates(own_scripts_dir, roots):
    """Cookie file locations, own skill first, then every root's quark-drive.

    Callers keep their own read policy: preflight.py only stats the file
    (size > 0) and never opens it, the downloader reads the value.
    """
    out = []
    if own_scripts_dir:
        out.append(Path(own_scripts_dir) / "cookie.txt")
    for r in roots:
        out.append(Path(r).joinpath(*COOKIE_RELPATH))
    return _dedupe(out)


def find_skill(skill_name, roots):
    """Return ``(skill_dir, root)`` for the first root holding that skill.

    ``(None, None)`` when absent everywhere. Purely a filesystem read.
    """
    for r in roots:
        cand = Path(r) / skill_name
        try:
            if (cand / SKILL_MARKER).is_file():
                return cand, Path(r)
        except Exception:
            pass
    return None, None

#!/usr/bin/env bash
# Zero-dependency environment bootstrap for quark-share-skill-installer
# (macOS / Linux / Git Bash). Pure ASCII on purpose.
#
# Resolves a usable Python 3.9+ in this order:
#   1. --python / $QUARK_INSTALLER_PYTHON (explicit override)
#   2. WorkBuddy bundled CPython (WORKBUDDY_RESOURCES_PATH / WORKBUDDY_APP_PATH
#      / standard macOS & Linux install roots)
#   3. WorkBuddy managed Python under ~/.workbuddy/binaries/python/versions
#   4. PATH: python3 / python; common system locations
#   5. A previously provisioned portable runtime
#   6. Auto-provision via `uv python install 3.12` (kept inside the runtime dir),
#      or a tarball from $QSI_PORTABLE_PYTHON_URL when supplied.
# Then invokes scripts/preflight.py and forwards its JSON report verbatim.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PREFLIGHT="$SKILL_DIR/scripts/preflight.py"

LOG=()
note() { LOG+=("$1"); }

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

emit_fallback() {
    local reason="$1" logs="" l
    if [ ${#LOG[@]} -gt 0 ]; then
        for l in "${LOG[@]}"; do
            [ -n "$logs" ] && logs="$logs, "
            logs="$logs\"$(json_escape "$l")\""
        done
    fi
    printf '{"ok":false,"ready":false,"error":"%s","python":{"cmd":"","version":"","source":"none","portable":false},"bootstrap_log":[%s],"blockers":["%s"],"hints":["Set QUARK_INSTALLER_PYTHON to an absolute path of Python 3.9+","WorkBuddy ships one under resources/vendor/python/","On macOS: brew install python@3.12 ; on Linux: use the distro package manager or uv python install 3.12","Then re-run this bootstrap script."]}\n' \
        "$(json_escape "$reason")" "$logs" "$(json_escape "$reason")"
}

# ---- args -------------------------------------------------------------------
NOFIX=0; VERBOSE=0; SKIPNET=0; PREPGUI=0; ASCII=0
LOCALZIP=""; COOKIEFILE=""; PY_OVERRIDE=""; SKILL_DIR_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-fix)        NOFIX=1; shift ;;
        --verbose)       VERBOSE=1; shift ;;
        --skip-network)  SKIPNET=1; shift ;;
        --prepare-gui)   PREPGUI=1; shift ;;
        --ascii-json)    ASCII=1; shift ;;
        --local-zip)     LOCALZIP="${2:-}"; shift 2 ;;
        --cookie-file)   COOKIEFILE="${2:-}"; shift 2 ;;
        --python)        PY_OVERRIDE="${2:-}"; shift 2 ;;
        --skill-dir)     SKILL_DIR_ARG="${2:-}"; shift 2 ;;
        *)               shift ;;
    esac
done
if [ -n "$SKILL_DIR_ARG" ]; then
    SKILL_DIR="$SKILL_DIR_ARG"
    PREFLIGHT="$SKILL_DIR/scripts/preflight.py"
fi
if [ ! -f "$PREFLIGHT" ]; then
    emit_fallback "preflight.py is missing: $PREFLIGHT"
    exit 1
fi

to_posix() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -u "$1" 2>/dev/null || printf '%s' "$1"
    else
        printf '%s' "$1"
    fi
}

CFG="$(to_posix "${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}")"
RUNTIME_DIR="$CFG/runtimes/quark-installer"
# Everything this skill writes lives under $RUNTIME_DIR. ~/Downloads is only
# READ (scanned for a zip the user downloaded themselves); never written to.
DOWNLOAD_DIR="$RUNTIME_DIR/downloads"
SCAN_DIRS="$HOME/Downloads"
# Install into the SAME skills root this skill was loaded from, not a hardcoded
# ~/.workbuddy/skills: different hosts mount skills under different roots
# (~/.workbuddy/skills, a per-workspace .skills dir, etc.). Fall back to the
# config dir only when the parent does not look like a skills root.
SKILLS_DIR="$(dirname "$SKILL_DIR")"
# Compare case-insensitively, like preflight.py (name.lower()) and like
# PowerShell's case-insensitive -match. A `*/Skills|*/SKILLS` root would
# otherwise be rejected here and fall back to a root the host never reads.
SKILLS_LEAF="$(basename "$SKILLS_DIR" | tr '[:upper:]' '[:lower:]')"
case "$SKILLS_LEAF" in
    skills|.skills) : ;;
    *) SKILLS_DIR="$CFG/skills" ;;
esac

# ---- collect candidates -----------------------------------------------------
CAND=()
add_cand() { if [ -n "$1" ] && [ -f "$1" ]; then CAND+=("$1|$2"); fi; }

# 1. explicit override
OVR="${PY_OVERRIDE:-${QUARK_INSTALLER_PYTHON:-}}"
if [ -n "$OVR" ]; then add_cand "$(to_posix "$OVR")" "explicit_override"; fi

# 2. WorkBuddy bundled vendor Python
RES="${WORKBUDDY_RESOURCES_PATH:-}"
if [ -z "$RES" ] && [ -n "${WORKBUDDY_APP_PATH:-}" ]; then
    RES="$(dirname "$(to_posix "$WORKBUDDY_APP_PATH")")"
fi
b="$(to_posix "$RES")"
if [ -n "$b" ]; then
    add_cand "$b/vendor/python/python.exe"     "workbuddy_vendor"
    add_cand "$b/vendor/python/python3.exe"    "workbuddy_vendor"
    add_cand "$b/vendor/python/bin/python3"    "workbuddy_vendor"
    add_cand "$b/vendor/python/bin/python3.13" "workbuddy_vendor"
    add_cand "$b/vendor/python/bin/python3.12" "workbuddy_vendor"
fi
for b in "/Applications/WorkBuddy.app/Contents/Resources" \
         "$HOME/Applications/WorkBuddy.app/Contents/Resources" \
         "/opt/WorkBuddy/resources" "/usr/share/workbuddy/resources"; do
    add_cand "$b/vendor/python/bin/python3"    "workbuddy_vendor"
    add_cand "$b/vendor/python/bin/python3.13" "workbuddy_vendor"
    add_cand "$b/vendor/python/bin/python3.12" "workbuddy_vendor"
done

# 3. WorkBuddy managed Python
if [ -d "$CFG/binaries/python/versions" ]; then
    for d in $(ls -1r "$CFG/binaries/python/versions" 2>/dev/null); do
        p="$CFG/binaries/python/versions/$d"
        add_cand "$p/bin/python3"  "workbuddy_managed"
        add_cand "$p/bin/python"   "workbuddy_managed"
        add_cand "$p/python.exe"   "workbuddy_managed"
        add_cand "$p/python"       "workbuddy_managed"
    done
fi

# 4. PATH interpreters
for n in python3 python; do
    p="$(command -v "$n" 2>/dev/null || true)"
    [ -n "$p" ] && add_cand "$p" "system_path"
done

# 5. common installs + previously provisioned runtimes
for p in /usr/local/bin/python3 /usr/bin/python3 /opt/homebrew/bin/python3 \
         "$HOME/.pyenv/shims/python3" /opt/python/bin/python3; do
    add_cand "$p" "common_install"
done
if [ -d "$RUNTIME_DIR" ]; then
    for d in "$RUNTIME_DIR"/python-*-embed-* "$RUNTIME_DIR"/python-*-standalone-* "$RUNTIME_DIR"/portable-url; do
        [ -d "$d" ] || continue
        add_cand "$d/python.exe"  "reused_runtime"
        add_cand "$d/python"      "reused_runtime"
        add_cand "$d/bin/python3" "reused_runtime"
    done
    if [ -d "$RUNTIME_DIR/pythons" ]; then
        for f in $(find "$RUNTIME_DIR/pythons" -type f -name 'python3*' 2>/dev/null | head -20); do
            add_cand "$f" "reused_runtime"
        done
    fi
fi

# ---- validate candidates ----------------------------------------------------
PROBE='import sys,ssl,zipfile,urllib.request,json,argparse,pathlib;print(sys.version_info[:3])'
test_python() {
    local p="$1" out v maj min
    [ -f "$p" ] || return 1
    out="$("$p" -c "$PROBE" 2>/dev/null)" || return 1
    v="$(printf '%s' "$out" | sed -n 's/.*(\([0-9][0-9]*\), *\([0-9][0-9]*\), *\([0-9][0-9]*\)).*/\1.\2.\3/p' | head -1)"
    [ -z "$v" ] && return 1
    maj="${v%%.*}"
    min="$(printf '%s' "${v#*.}" | cut -d. -f1)"
    if [ "$maj" -gt 3 ] 2>/dev/null; then
        :
    elif [ "$maj" -eq 3 ] 2>/dev/null && [ "$min" -ge 9 ] 2>/dev/null; then
        :
    else
        return 1
    fi
    printf '%s' "$v"
}

PY=""; SRC=""; VER=""
if [ ${#CAND[@]} -gt 0 ]; then
    for c in "${CAND[@]}"; do
        p="${c%%|*}"; s="${c##*|}"
        v="$(test_python "$p")" || continue
        PY="$p"; SRC="$s"; VER="$v"
        note "Resolved Python $v from $s ($p)"
        break
    done
fi

# ---- auto-provision via uv (OPT-IN, kept inside our runtime dir) ------------
# `uv python install` downloads a python-build-standalone build and verifies it
# against uv's own embedded hashes. This skill cannot re-verify that archive
# against a pinned fingerprint of its own, so the uv route is NOT part of the
# fail-closed guarantee: it is opt-in via QSI_ALLOW_UV=1 and its provenance is
# reported as "verified by uv, not by this skill".
if [ -z "$PY" ]; then
    if [ "${QSI_ALLOW_UV:-0}" = "1" ]; then
        note "No usable Python found; QSI_ALLOW_UV=1 so trying uv-based auto-provision (integrity provided by uv, not pinned here)"
        UV="$(command -v uv 2>/dev/null || true)"
        if [ -n "$UV" ]; then
            UV_VER="$("$UV" --version 2>/dev/null | head -1)"
            mkdir -p "$RUNTIME_DIR/pythons" 2>/dev/null || true
            if UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/pythons" "$UV" python install 3.12 >/dev/null 2>&1; then
                uvf="$(UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/pythons" "$UV" python find 3.12 2>/dev/null | head -1)"
                v="$(test_python "$uvf")" || v=""
                if [ -n "$v" ]; then
                    PY="$uvf"; SRC="uv_provisioned"; VER="$v"
                    note "Provisioned Python $v via uv at $uvf ($UV_VER; uv-verified, no pinned fingerprint)"
                fi
            fi
        else
            note "QSI_ALLOW_UV=1 but uv is not installed; skipping uv provisioning"
        fi
    else
        note "Skipping uv auto-provision: not enabled (set QSI_ALLOW_UV=1 to allow it; uv-verified, not fingerprint-pinned by this skill)"
    fi
fi

# ---- optional tarball URL (enterprise mirror / air-gapped staging) ----------
# Fail closed: an override interpreter is executable code, so a caller-supplied
# SHA256 is mandatory. Without it, nothing is downloaded or executed.
if [ -z "$PY" ] && [ -n "${QSI_PORTABLE_PYTHON_URL:-}" ]; then
    TB_URL="$QSI_PORTABLE_PYTHON_URL"
    TB_SHA="${QSI_PORTABLE_PYTHON_SHA256:-}"
    if [ "${TB_URL#https://}" = "$TB_URL" ]; then
        note "refusing non-HTTPS QSI_PORTABLE_PYTHON_URL"
    elif ! printf '%s' "$TB_SHA" | grep -Eq '^[0-9a-fA-F]{64}$'; then
        note "QSI_PORTABLE_PYTHON_URL is set but QSI_PORTABLE_PYTHON_SHA256 is missing or invalid; refusing an unverifiable download"
    elif ! command -v curl >/dev/null 2>&1; then
        note "curl unavailable; cannot fetch QSI_PORTABLE_PYTHON_URL"
    elif ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
        note "no sha256 tool (sha256sum/shasum); refusing an unverifiable download"
    else
        note "Trying QSI_PORTABLE_PYTHON_URL (SHA256 pinned)"
        dest="$RUNTIME_DIR/portable-url"
        tarball="$RUNTIME_DIR/_download/portable.tar.gz"
        part="$tarball.part"
        mkdir -p "$dest" "$(dirname "$tarball")" 2>/dev/null || true
        if curl -fsSL --max-time 180 -o "$part" "$TB_URL" 2>/dev/null; then
            if command -v sha256sum >/dev/null 2>&1; then
                got="$(sha256sum "$part" | awk '{print $1}')"
            else
                got="$(shasum -a 256 "$part" | awk '{print $1}')"
            fi
            want="$(printf '%s' "$TB_SHA" | tr 'A-F' 'a-f')"
            if [ "$got" != "$want" ]; then
                rm -f "$part" 2>/dev/null || true
                note "Tarball rejected: sha256 mismatch (nothing extracted)"
            else
                mv -f "$part" "$tarball" 2>/dev/null || true
                if tar -xzf "$tarball" -C "$dest" 2>/dev/null; then
                    found="$(find "$dest" -type f \( -name python3 -o -name python \) 2>/dev/null | head -1)"
                    [ -z "$found" ] && found="$(find "$dest" -type f -name 'python3*' 2>/dev/null | head -1)"
                    v="$(test_python "$found")" || v=""
                    if [ -n "$v" ]; then
                        PY="$found"; SRC="portable_url"; VER="$v"
                        note "Provisioned Python $v from QSI_PORTABLE_PYTHON_URL (sha256 verified)"
                    else
                        note "Tarball extracted but no working python found inside"
                    fi
                else
                    note "Tarball extraction failed"
                fi
            fi
        else
            note "Download from QSI_PORTABLE_PYTHON_URL failed"
        fi
    fi
fi

if [ -z "$PY" ]; then
    emit_fallback "Unable to locate or auto-provision a usable Python 3.9+ interpreter. Install Python 3.9+ (macOS: brew install python@3.12 ; Linux: distro package manager or uv python install 3.12), or set QUARK_INSTALLER_PYTHON."
    exit 1
fi

# ---- hand off to preflight.py ----------------------------------------------
export QSI_PYTHON_SOURCE="$SRC"
# Derived from the source, not hardcoded: an interpreter this skill installed
# itself (uv-provisioned or the pinned tarball) is portable by definition, and
# reporting portable=false for it would contradict python.source.
case "$SRC" in
    uv_provisioned|portable_url|portable_downloaded|reused_runtime) QSI_PORTABLE=1 ;;
    *) QSI_PORTABLE=0 ;;
esac
export QSI_PYTHON_PORTABLE="$QSI_PORTABLE"
QSI_LOG_JOINED=""
if [ ${#LOG[@]} -gt 0 ]; then
    for l in "${LOG[@]}"; do
        if [ -z "$QSI_LOG_JOINED" ]; then QSI_LOG_JOINED="$l"; else QSI_LOG_JOINED="$QSI_LOG_JOINED||$l"; fi
    done
fi
export QSI_BOOTSTRAP_LOG="$QSI_LOG_JOINED"
export QSI_RUNTIME_DIR="$RUNTIME_DIR"
export QSI_DOWNLOAD_DIR="$DOWNLOAD_DIR"
export QSI_SKILLS_DIR="$SKILLS_DIR"
[ -n "$LOCALZIP" ]   && export QSI_LOCAL_ZIP="$LOCALZIP"
[ -n "$COOKIEFILE" ] && export QSI_COOKIE_FILE="$COOKIEFILE"

REPORT_FILE="$RUNTIME_DIR/last_preflight.json"
ARGS=(--json)
[ "$NOFIX" -eq 1 ]   && ARGS+=(--no-fix)
[ "$SKIPNET" -eq 1 ] && ARGS+=(--skip-network)
[ "$PREPGUI" -eq 1 ] && ARGS+=(--prepare-gui)
[ "$ASCII" -eq 1 ]   && ARGS+=(--ascii-json)
[ -n "$LOCALZIP" ]   && ARGS+=(--local-zip "$LOCALZIP")
[ -n "$COOKIEFILE" ] && ARGS+=(--cookie-file "$COOKIEFILE")
ARGS+=(--python-source "$SRC")
ARGS+=(--report-file "$REPORT_FILE")

OUT="$("$PY" "$PREFLIGHT" "${ARGS[@]}" 2>/dev/null)"
RC=$?
if [ "$VERBOSE" -eq 1 ] && [ ${#LOG[@]} -gt 0 ]; then
    for l in "${LOG[@]}"; do printf '[bootstrap] %s\n' "$l" >&2; done
fi
case "$OUT" in
    \{*) printf '%s\n' "$OUT" ;;
    *)   emit_fallback "preflight.py produced no JSON (exit=$RC)"; exit 1 ;;
esac

#!/usr/bin/env bash
# Zero-dependency environment bootstrap for itest-assistant
# (Git Bash on Windows / macOS / Linux). Pure ASCII on purpose.
#
# Resolves a usable Node.js 16+ in this order:
#   1. --node / $ITEST_NODE_BIN / $NODE_BIN (explicit override)
#   2. Persisted stage-P runtime (~/.workbuddy/runtimes/itest-assistant/node_path.txt)
#   3. WorkBuddy managed Node under ~/.workbuddy/binaries/node/versions
#   4. $CODEBUDDY_NODE_BIN
#   5. PATH: node / node.exe
#   6. WorkBuddy bundled vendor/node.zip (no download, Windows Git Bash)
#   7. Auto-download official portable Node tarball from mirrors
# Then invokes scripts/preflight.js and forwards its JSON verbatim.
#
# NOTE: the desktop action layer is Windows PowerShell 5.1 + Win32 only.
# On macOS / Linux this bootstrap still runs and preflight reports a clear
# `platform` block instead of crashing.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PREFLIGHT="$SKILL_DIR/scripts/preflight.js"

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
    printf '{"ok":false,"ready":false,"stage":"P","error":"%s","node":{"cmd":"","version":"","source":"none","portable":false},"run":{"node_cmd":""},"route":"block","route_reason":"%s","bootstrap_log":[%s],"blockers":["%s"],"hints":["Set ITEST_NODE_BIN or NODE_BIN to an absolute path of Node 16+.","WorkBuddy ships Node under ~/.workbuddy/binaries/node/versions"],"checks":[],"auto_fixed":[],"report_file":""}\n' \
        "$(json_escape "$reason")" "$(json_escape "$reason")" "$logs" "$(json_escape "$reason")"
}

# ---- args -------------------------------------------------------------------
NOFIX=0; VERBOSE=0; SKIPNET=0; READABLE=0; FORCEPORTABLE=0
NODE_OVERRIDE=""; SKILL_DIR_ARG=""; RUNTIME_DIR_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-fix)        NOFIX=1; shift ;;
        --verbose)       VERBOSE=1; shift ;;
        --skip-network) SKIPNET=1; shift ;;
        --readable)      READABLE=1; shift ;;
        --force-portable) FORCEPORTABLE=1; shift ;;
        --node)          NODE_OVERRIDE="${2:-}"; shift 2 ;;
        --skill-dir)     SKILL_DIR_ARG="${2:-}"; shift 2 ;;
        --runtime-dir)   RUNTIME_DIR_ARG="${2:-}"; shift 2 ;;
        *)               shift ;;
    esac
done
if [ -n "$SKILL_DIR_ARG" ]; then
    SKILL_DIR="$SKILL_DIR_ARG"
    PREFLIGHT="$SKILL_DIR/scripts/preflight.js"
fi
if [ ! -f "$PREFLIGHT" ]; then
    emit_fallback "preflight.js is missing: $PREFLIGHT"
    exit 1
fi

CFG="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}"
if [ -n "$RUNTIME_DIR_ARG" ]; then RUNTIME_DIR="$RUNTIME_DIR_ARG"
else RUNTIME_DIR="$CFG/runtimes/itest-assistant"; fi
NODE_PATH_FILE="$RUNTIME_DIR/node_path.txt"
REPORT_FILE="$RUNTIME_DIR/last_preflight.json"

# ---- collect candidates -----------------------------------------------------
CAND=()
add_cand() { if [ -n "$1" ] && [ -f "$1" ]; then CAND+=("$1|$2"); fi; }

OVR="${NODE_OVERRIDE:-${ITEST_NODE_BIN:-${NODE_BIN:-}}}"
if [ -n "$OVR" ]; then add_cand "$OVR" "explicit_override"; fi

# persisted stage-P runtime (survives across separate tool calls)
if [ -f "$NODE_PATH_FILE" ]; then
    saved="$(tr -d '\r\n' < "$NODE_PATH_FILE")"
    if [ -n "$saved" ]; then add_cand "$saved" "reused_runtime"; fi
fi

# WorkBuddy managed Node
if [ -d "$CFG/binaries/node/versions" ]; then
    for d in $(ls -1r "$CFG/binaries/node/versions" 2>/dev/null); do
        p="$CFG/binaries/node/versions/$d"
        add_cand "$p/node.exe" "workbuddy_managed"
        add_cand "$p/node"     "workbuddy_managed"
    done
fi

if [ -n "${CODEBUDDY_NODE_BIN:-}" ]; then add_cand "$CODEBUDDY_NODE_BIN" "workbuddy_cli"; fi

for n in node.exe node; do
    p="$(command -v "$n" 2>/dev/null || true)"
    [ -n "$p" ] && add_cand "$p" "system_path"
done

for p in /usr/local/bin/node /usr/bin/node /opt/homebrew/bin/node \
         "/c/Program Files/nodejs/node.exe" "/c/nodejs/node.exe"; do
    add_cand "$p" "common_install"
done

# ---- validate candidates (current-shell loop, NOT a pipe: keeps results) -----
PROBE='process.stdout.write(process.versions.node)'
test_node() {
    local p="$1" out v maj
    [ -f "$p" ] || return 1
    out="$("$p" -e "$PROBE" 2>/dev/null)" || return 1
    v="$(printf '%s' "$out" | sed -n 's/^v\?\([0-9][0-9]*\)\.\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1.\2.\3/p' | head -1)"
    [ -z "$v" ] && return 1
    maj="${v%%.*}"
    if [ "$maj" -lt 16 ] 2>/dev/null; then return 1; fi
    printf '%s' "$v"
}

NODE=""; SRC=""; VER=""; PORTABLE=0
if [ "$FORCEPORTABLE" -eq 1 ]; then
    note '--force-portable: skipping interpreter discovery, provisioning a portable runtime'
elif [ ${#CAND[@]} -gt 0 ]; then
    for c in "${CAND[@]}"; do
        p="${c%%|*}"; s="${c##*|}"
        v="$(test_node "$p")" || continue
        NODE="$p"; SRC="$s"; VER="$v"
        note "Resolved Node $v from $s ($p)"
        break
    done
fi

# ---- WorkBuddy bundled vendor/node.zip (no network needed) ------------------
if [ -z "$NODE" ]; then
    RES="${WORKBUDDY_RESOURCES_PATH:-}"
    if [ -z "$RES" ] && [ -n "${WORKBUDDY_APP_PATH:-}" ]; then
        RES="$(dirname "$WORKBUDDY_APP_PATH")"
    fi
    VENDOR_ZIP=""
    [ -n "$RES" ] && VENDOR_ZIP="$RES/vendor/node.zip"
    if [ -n "$VENDOR_ZIP" ] && [ -f "$VENDOR_ZIP" ] && command -v unzip >/dev/null 2>&1; then
        VDEST="$RUNTIME_DIR/node-vendor"
        cached="$(find "$VDEST" -type f -name 'node.exe' 2>/dev/null | head -1)"
        if [ -z "$cached" ]; then
            mkdir -p "$VDEST" 2>/dev/null || true
            unzip -oq "$VENDOR_ZIP" -d "$VDEST" 2>/dev/null || true
            cached="$(find "$VDEST" -type f \( -name 'node.exe' -o -name node \) 2>/dev/null | head -1)"
        fi
        if [ -n "$cached" ]; then
            v="$(test_node "$cached")" || v=""
            if [ -n "$v" ]; then
                NODE="$cached"; SRC="workbuddy_vendor_zip"; VER="$v"; PORTABLE=1
                note "Unpacked WorkBuddy bundled Node $v ($cached)"
            fi
        fi
    fi
fi

# ---- auto-download official portable Node (last resort) --------------------
if [ -z "$NODE" ] && command -v curl >/dev/null 2>&1; then
    note "No usable Node found; preparing a portable runtime automatically"
    NVER="22.14.0"
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*) OS="win";   EXT="zip";    ARCH="x64" ;;
        Darwin)               OS="darwin"; EXT="tar.gz"; ARCH="arm64" ;;
        *)                    OS="linux";  EXT="tar.xz"; ARCH="x64" ;;
    esac
    case "$(uname -m 2>/dev/null)" in
        aarch64|arm64) ARCH="arm64" ;;
        x86_64|amd64)  ARCH="x64" ;;
    esac
    if [ "$OS" = "win" ]; then
        NAME="node-v$NVER-win-$ARCH"; PKG="$NAME.zip"; EXE="node.exe"
    else
        NAME="node-v$NVER-$OS-$ARCH"; PKG="$NAME.tar.xz"; EXE="node"
        [ "$OS" = "darwin" ] && PKG="$NAME.tar.gz"
    fi
    DEST="$RUNTIME_DIR/$NAME"
    DOWNLOADED=0
    cached="$(find "$DEST" -type f \( -name node.exe -o -name node \) 2>/dev/null | head -1)"
    if [ -n "$cached" ]; then
        note "Reusing previously downloaded portable Node at $DEST"
    else
        mkdir -p "$RUNTIME_DIR/_download" 2>/dev/null || true
        PKGPATH="$RUNTIME_DIR/_download/$PKG"
        MIRRORS=(
            "https://mirrors.huaweicloud.com/nodejs/v$NVER/$PKG"
            "https://registry.npmmirror.com/-/binary/node/v$NVER/$PKG"
            "https://nodejs.org/dist/v$NVER/$PKG"
        )
        for u in "${MIRRORS[@]}"; do
            if curl -fsSL --max-time 180 -o "$PKGPATH" "$u" 2>/dev/null; then
                DOWNLOADED=1
                note "Downloaded portable Node from $u"
                break
            else
                note "Mirror failed: $u"
            fi
        done
        if [ "$DOWNLOADED" -eq 1 ]; then
            mkdir -p "$DEST" 2>/dev/null || true
            if [ "$EXT" = "zip" ]; then
                unzip -oq "$PKGPATH" -d "$RUNTIME_DIR" 2>/dev/null || true
            else
                tar -xJf "$PKGPATH" -C "$RUNTIME_DIR" 2>/dev/null || \
                tar -xzf "$PKGPATH" -C "$RUNTIME_DIR" 2>/dev/null || true
            fi
            cached="$(find "$DEST" -type f \( -name node.exe -o -name node \) 2>/dev/null | head -1)"
            [ -n "$cached" ] && note "Extracted portable Node to $DEST"
        fi
    fi
    if [ -n "$cached" ]; then
        v="$(test_node "$cached")" || v=""
        if [ -n "$v" ]; then
            NODE="$cached"; VER="$v"; PORTABLE=1
            # Lesson learned: a reused cached runtime must NOT be called downloaded.
            if [ "$DOWNLOADED" -eq 1 ]; then SRC="portable_downloaded"; else SRC="reused_runtime"; fi
            note "Portable Node ready: $cached ($v)"
        fi
    fi
fi

if [ -z "$NODE" ]; then
    emit_fallback "Unable to locate or auto-provision a usable Node 16+ interpreter (offline and no bundled runtime)."
    exit 1
fi

# ---- persist resolution so later run.sh calls reuse it ----------------------
mkdir -p "$RUNTIME_DIR" 2>/dev/null || true
printf '%s' "$NODE" > "$NODE_PATH_FILE" 2>/dev/null || true
note "Persisted node path to $NODE_PATH_FILE"

# ---- hand off to preflight.js ----------------------------------------------
export ITEST_NODE_SOURCE="$SRC"
export ITEST_NODE_PORTABLE="$PORTABLE"
JOINED=""
if [ ${#LOG[@]} -gt 0 ]; then
    for l in "${LOG[@]}"; do
        if [ -z "$JOINED" ]; then JOINED="$l"; else JOINED="$JOINED||$l"; fi
    done
fi
export ITEST_BOOTSTRAP_LOG="$JOINED"
export ITEST_RUNTIME_DIR="$RUNTIME_DIR"

ARGS=(--report-file "$REPORT_FILE" --runtime-dir "$RUNTIME_DIR")
[ "$NOFIX" -eq 1 ]   && ARGS+=(--no-fix)
[ "$SKIPNET" -eq 1 ] && ARGS+=(--skip-network)
[ "$READABLE" -eq 1 ] && ARGS+=(--readable)

OUT="$("$NODE" "$PREFLIGHT" "${ARGS[@]}" 2>/dev/null)"
RC=$?
if [ "$VERBOSE" -eq 1 ] && [ ${#LOG[@]} -gt 0 ]; then
    for l in "${LOG[@]}"; do printf '[bootstrap] %s\n' "$l" >&2; done
fi
case "$OUT" in
    \{*) printf '%s\n' "$OUT" ;;
    *)   emit_fallback "preflight.js produced no JSON (exit=$RC)"; exit 1 ;;
esac

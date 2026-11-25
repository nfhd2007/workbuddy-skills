#!/usr/bin/env bash
# iTEST 助手统一入口（阶段 P 增强版，向后兼容）。
#
#   bash scripts/run.sh doctor [--json]        用已解析的运行时复检环境（不下载、不修 BOM 之外的东西）
#   bash scripts/run.sh scale  --auto --coords "1078,135"   跨分辨率坐标粗换算
#   bash scripts/run.sh info | shot | uia | clock | budget | guard | fill | submit | cleanup ...
#   bash scripts/run.sh record --list         听力回环录制（可选，走 Python）
#
# 关键：阶段 P（bootstrap.ps1 / bootstrap.sh）解析出的 Node 会写到
#   ~/.workbuddy/runtimes/itest-assistant/node_path.txt
# 本脚本优先读它，保证「自动下载了便携 Node」之后，后续每一条 run.sh 命令
# 都能找到同一个解释器（环境变量不会跨工具调用存活）。
#
# 环境变量覆盖：NODE_BIN / PY_BIN / ITEST_PS / ITEST_TITLE / WORKBUDDY_CONFIG_DIR
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="${1:-info}"

CFG="${WORKBUDDY_CONFIG_DIR:-$HOME/.workbuddy}"
RUNTIME_DIR="$CFG/runtimes/itest-assistant"

find_node() {
  if [ -n "${NODE_BIN:-}" ]; then echo "$NODE_BIN"; return; fi
  if [ -n "${ITEST_NODE_BIN:-}" ]; then echo "$ITEST_NODE_BIN"; return; fi
  # 阶段 P 持久化的运行时优先（可能是自动下载的便携版，不在 PATH 里）
  if [ -f "$RUNTIME_DIR/node_path.txt" ]; then
    local saved
    saved="$(tr -d '\r\n' < "$RUNTIME_DIR/node_path.txt")"
    if [ -n "$saved" ] && [ -x "$saved" ]; then echo "$saved"; return; fi
  fi
  local c
  for c in \
    "$CFG"/binaries/node/versions/*/node.exe \
    "$CFG"/binaries/node/versions/*/node \
    "$RUNTIME_DIR"/node-*/node.exe \
    "$RUNTIME_DIR"/node-*/bin/node \
    "${CODEBUDDY_NODE_BIN:-}" \
    "$(command -v node 2>/dev/null || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return; }
  done
  echo ""
}

find_python() {
  if [ -n "${PY_BIN:-}" ]; then echo "$PY_BIN"; return; fi
  local c
  for c in \
    "${WORKBUDDY_RESOURCES_PATH:-/nonexistent}/vendor/python/python.exe" \
    "$CFG"/binaries/python/versions/*/python \
    "$CFG"/binaries/python/versions/*/python.exe \
    "$(command -v python3 2>/dev/null || true)" \
    "$(command -v python 2>/dev/null || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return; }
  done
  echo ""
}

require() {
  local bin="$1" name="$2" envname="$3"
  if [ -z "$bin" ]; then
    echo "未找到 $name。请先运行阶段 P（bash scripts/bootstrap.sh 或 bootstrap.ps1）自动准备；也可设置 $envname 环境变量指定路径。" >&2
    exit 1
  fi
}

NODE="$(find_node)"

case "$CMD" in
  record)
    shift
    PY="$(find_python)"; require "$PY" "Python（仅听力录制需要）" "PY_BIN"
    exec "$PY" "$DIR/record_loopback.py" "$@"
    ;;
  doctor|preflight)
    # 复检：默认不做修复（--fix 才修 BOM / 目录），输出结构化 JSON。
    shift
    require "$NODE" "Node.js" "NODE_BIN"
    exec "$NODE" "$DIR/preflight.js" "$@"
    ;;
  scale)
    shift
    require "$NODE" "Node.js" "NODE_BIN"
    exec "$NODE" "$DIR/scale.js" "$@"
    ;;
  *)
    require "$NODE" "Node.js" "NODE_BIN"
    exec "$NODE" "$DIR/itest.js" "$@"
    ;;
esac

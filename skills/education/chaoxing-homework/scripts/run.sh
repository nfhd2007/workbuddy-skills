#!/usr/bin/env bash
# 包装 cx.js：自动定位 node 与 playwright-core，免去每次设置 NODE_PATH。
# 用法: scripts/run.sh extract --out /tmp/q.json
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NODE_BIN="${NODE_BIN:-}"
if [ -z "$NODE_BIN" ]; then
  for c in \
    "$HOME/.workbuddy/binaries/node/versions/22.22.2-6/node.exe" \
    "$(command -v node 2>/dev/null || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && NODE_BIN="$c" && break
  done
fi
[ -z "$NODE_BIN" ] && { echo "未找到 node，可设置 NODE_BIN 环境变量"; exit 1; }

# playwright-core 所在目录（已装好的共享 node_modules）
for m in \
  "$HOME/.workbuddy/binaries/node/workspace/node_modules" \
  "$DIR/../node_modules"; do
  [ -d "$m/playwright-core" ] && NODE_PATH="$m${NODE_PATH:+;$NODE_PATH}" && break
done
export NODE_PATH
exec "$NODE_BIN" "$DIR/cx.js" "$@"

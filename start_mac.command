#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$DIR/.venv/bin/python"

pick_python() {
  for py in python3.12 python3.11 python3.10; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

PY_BIN="$(pick_python || true)"

if [ -z "$PY_BIN" ]; then
  osascript -e 'display dialog "未检测到 Python 3.10~3.12。请先安装（推荐 Miniconda: conda create -n npc_tts_py311 python=3.11）" buttons {"OK"} default button "OK" with icon stop'
  exit 1
fi

# 1) 首次运行时执行完整 bootstrap（创建 venv、克隆第三方仓库等）
if [ ! -x "$VENV_PY" ]; then
  "$PY_BIN" "$DIR/bootstrap.py"
fi

# 2) 强制使用项目 .venv 运行，避免 macOS 外部管理环境冲突
if [ ! -x "$VENV_PY" ]; then
  osascript -e 'display dialog "未找到 .venv Python，可尝试手动运行：python bootstrap.py" buttons {"OK"} default button "OK" with icon stop'
  exit 1
fi

# 3) 每次启动都同步 requirements.txt，确保新增依赖（如 websockets）自动安装
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

"$VENV_PY" "$DIR/run_dev.py"

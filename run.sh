#!/bin/bash
# ZD 报价助手 - Mac 启动器
# 用法：双击本文件，或在终端执行 ./run.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="/Users/mac/.workbuddy/binaries/python/envs/default"
if [ ! -x "$VENV/bin/python" ]; then
  echo "未找到虚拟环境，请先运行一次依赖安装。"
  exit 1
fi
exec "$VENV/bin/python" "$DIR/zd_app.py"

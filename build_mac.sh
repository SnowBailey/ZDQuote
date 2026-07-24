#!/bin/bash
# ZDQuote · macOS 打包脚本（生成可直接运行的 .app）
# 用法：./build_mac.sh
# 依赖：本机已装 pyinstaller + pillow（在托管 venv 中）
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="/Users/mac/.workbuddy/binaries/python/envs/default"
PY="$VENV/bin/python"
PKG="$VENV/lib/python3.13/site-packages"

APP_NAME="ZDQuote"
ENTRY="$DIR/zd_app.py"
ICON="$DIR/ZDQuote.icns"
CTK_ASSETS="$PKG/customtkinter/assets"

if [ ! -x "$PY" ]; then
  echo "未找到 Python 环境：$PY"
  exit 1
fi
if [ ! -f "$ICON" ]; then
  echo "缺少图标 $ICON，先运行：PYTHONPATH=$DIR $PY $DIR/make_icon.py"
  exit 1
fi

echo ">>> 使用 Python: $PY"
echo ">>> 入口: $ENTRY"

"$PY" -m PyInstaller \
  --name "$APP_NAME" \
  --windowed \
  --icon "$ICON" \
  --osx-bundle-identifier "com.zdquote.app" \
  --paths "$DIR" \
  --add-data "$CTK_ASSETS:customtkinter/assets" \
  --hidden-import customtkinter \
  --hidden-import openpyxl \
  --hidden-import msoffcrypto \
  --hidden-import cryptography \
  --hidden-import olefile \
  --hidden-import zd_config \
  --hidden-import zd_db \
  --hidden-import zd_excel \
  --hidden-import zd_pricing \
  --hidden-import zd_decrypt \
  --hidden-import zd_wechat \
  --clean --noconfirm \
  "$ENTRY"

echo ""
echo ">>> 构建完成：dist/$APP_NAME.app"

# 立即做 ad-hoc 签名，避免双击被 Gatekeeper 直接拦截
if command -v codesign >/dev/null 2>&1; then
  echo ">>> ad-hoc 签名中..."
  codesign --force --deep --sign - "dist/$APP_NAME.app" 2>&1 | tail -3 || \
    echo "（ad-hoc 签名失败，不影响使用；可在本机手动 xattr -dr com.apple.quarantine）"
fi

echo ">>> 输出目录: $DIR/dist"

"""ZDQuote · Windows 打包脚本（生成可直接运行的 ZDQuote.exe）。

用法（在 Windows 10 上）：
    python -m pip install -r requirements.txt
    python build_win.py
产物：dist\\ZDQuote\\ZDQuote.exe （含 Python + Tcl/Tk + 全部插件，自包含）

注：本脚本跨平台可解析，但 PyInstaller 不能交叉编译——
必须在目标系统（Windows）上运行，才会产出 Windows 可执行文件。
"""
import io
import os
import sys
import subprocess
import importlib.util

# Windows 控制台默认 cp1252，中文打印会 UnicodeEncodeError；强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def _customtkinter_assets() -> str:
    spec = importlib.util.find_spec("customtkinter")
    if spec is None or spec.origin is None:
        raise RuntimeError("未安装 customtkinter")
    assets = os.path.join(os.path.dirname(spec.origin), "assets")
    if not os.path.isdir(assets):
        raise RuntimeError(f"customtkinter assets 未找到: {assets}")
    return assets


def main():
    try:
        ctk_assets = _customtkinter_assets()
    except Exception as e:
        print("错误:", e)
        sys.exit(1)

    entry = os.path.join(HERE, "zd_app.py")
    if not os.path.isfile(entry):
        print(f"Error: missing entry file {entry}")
        sys.exit(1)
    icon = os.path.join(HERE, "ZDQuote.ico")
    if not os.path.isfile(icon):
        print("缺少图标 ZDQuote.ico，先运行：python make_icon_win.py")
        sys.exit(1)

    # --add-data 分隔符：Windows 用 ;，其它平台用 :
    sep = ";" if os.sep == "\\" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "ZDQuote",
        "--windowed",
        "--icon", icon,
        "--paths", HERE,
        "--add-data", f"{ctk_assets}{sep}customtkinter/assets",
        "--hidden-import", "customtkinter",
        "--hidden-import", "openpyxl",
        "--hidden-import", "msoffcrypto",
        "--hidden-import", "cryptography",
        "--hidden-import", "olefile",
        "--hidden-import", "zd_config",
        "--hidden-import", "zd_db",
        "--hidden-import", "zd_excel",
        "--hidden-import", "zd_pricing",
        "--hidden-import", "zd_decrypt",
        "--hidden-import", "zd_wechat",
        "--clean", "--noconfirm",
        entry,
    ]
    print(">>> 运行命令：")
    print("    " + " ".join(cmd))
    subprocess.check_call(cmd)

    dist = os.path.join(HERE, "dist", "ZDQuote")
    print("\n>>> 构建完成：", dist)
    print(">>> 主程序：", os.path.join(dist, "ZDQuote.exe"))
    if os.path.isfile(os.path.join(HERE, "installer_win.iss")):
        print(">>> 可选：用 Inno Setup 打开 installer_win.iss 编译成安装包 ZDQuote_Setup.exe")


if __name__ == "__main__":
    main()

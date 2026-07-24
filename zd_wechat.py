"""ZD 报价助手 - 微信转发（Mac）。

说明：微信 Mac 版没有可靠的免手动发送接口，这里做的是
“在 Finder 中显示文件 + 启动微信 + 尽力用 AppleScript 发到文件传输助手”。
若自动化发送因微信版本差异失败，会优雅降级并提示手动拖拽。
"""
import subprocess
import os
import sys
import tempfile


def reveal_in_finder(path):
    try:
        subprocess.run(["open", "-R", path], check=False)
        return True
    except Exception:
        return False


def launch_wechat():
    try:
        subprocess.run(["open", "-a", "WeChat"], check=False)
        return True
    except Exception:
        return False


def _applescript_for_filehelper(path):
    # 尽力把文件发到「文件传输助手」。UI 脚本对微信版本敏感，失败不抛异常。
    esc = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'''
set theFile to POSIX file "{esc}"
tell application "WeChat"
    activate
    delay 1
end tell
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        delay 0.5
        -- 点击左侧「文件传输助手」
        try
            set theRows to rows of table 1 of scroll area 1 of splitter group 1 of window 1
            repeat with r in theRows
                try
                    if value of static text 1 of r contains "文件传输助手" then
                        click r
                        exit repeat
                    end if
                end try
            end repeat
        end try
        delay 0.6
        -- 通过「拖拽文件到输入框」不可靠，改为用菜单发送文件
        try
            click menu item "发送文件" of menu "文件" of menu bar 1
            delay 0.8
            keystroke "G" using {{shift down, command down}}
            delay 0.4
            keystroke "{esc}"
            delay 0.4
            click button "前往" of sheet 1 of window 1
            delay 0.6
            click button "打开" of sheet 1 of window 1
        end try
    end tell
end tell
'''


def try_send_filehelper(path):
    """返回 (成功: bool, 详情: str)。永不抛异常。"""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".scpt", delete=False) as f:
            f.write(_applescript_for_filehelper(path))
            scpt = f.name
        res = subprocess.run(["osascript", scpt], capture_output=True, text=True,
                             timeout=25)
        os.unlink(scpt)
        if res.returncode == 0:
            return True, "已尝试通过 AppleScript 发送到文件传输助手。"
        return False, (res.stderr.strip() or "AppleScript 返回非零")[:120]
    except Exception as e:
        return False, f"发送脚本异常: {e}"[:120]


def forward(path):
    """综合转发：显示文件 + 启动微信 + 尽力发送。返回提示文案。"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"

    # Windows：无 AppleScript，只打开文件所在文件夹并提示手动发送
    if sys.platform.startswith("win"):
        try:
            os.startfile(os.path.dirname(path))  # 打开文件夹
        except Exception:
            pass
        return ("已为你打开文件所在文件夹。\n"
                "（Windows 版暂未集成微信自动发送，请把文件拖入微信对话窗口即可发送。）")

    # macOS：原逻辑（Finder 显示 + 启动微信 + 尽力 AppleScript 发送）
    reveal_in_finder(path)
    launch_wechat()
    ok, detail = try_send_filehelper(path)
    if ok:
        return "已为你打开文件并启动微信，并已尝试发送到「文件传输助手」。请在微信中确认发送。"
    return ("已为你打开文件所在位置并启动微信。\n"
            "（微信 Mac 版自动化发送受版本限制，未能自动完成，请把文件拖入对话窗口即可发送。）")

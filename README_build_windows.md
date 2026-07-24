# ZDQuote · Windows 10 打包与安装说明

> 由于 PyInstaller **不支持交叉编译**，macOS 上只能出 `.app`、出不了 Windows 的 `.exe`。
> 本目录已备好**一键打包工具包**，请在 **Windows 10（64 位）** 机器上完成最后这一步。

---

## 零、不想碰命令行？用 GitHub 云构建（推荐，零本地 Windows 要求）

仓库里已配好 `.github/workflows/build-windows.yml`：推一次代码，微软**免费 Windows 云服务器**自动把 `ZDQuote_Setup.exe` 打出来给你下载。

1. 在 GitHub 新建一个**空仓库**（如 `ZDQuote`）。
2. 在本项目目录依次执行（把 `<你的用户名>/<仓库名>` 换成你自己的）：
   ```bat
   cd ZDQuote
   git init
   git add .
   git commit -m "add ZDQuote"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. 打开仓库 → **Actions** → 等 `Build Windows Installer` 跑完（约 3~5 分钟）。
4. 点进该次运行 → **Artifacts** → 下载 `ZDQuote_Setup.zip`，解压得到 `ZDQuote_Setup.exe` 即为安装包。

> 若 Inno Setup 那步失败，工作流会兜底上传 `ZDQuote_portable` 成品文件夹，照样能直接运行。

---

## 一、准备（一次性）

1. 下载并安装 **Python 3.10+**（官网 python.org）。
   - 安装时务必勾选 **`Add Python to PATH`**。
2. 把本目录（`ZDQuote` 整个文件夹）拷贝到 Windows 机器上任意位置，例如 `D:\ZDQuote\`。
3. （可选，做安装包才需要）下载安装 **Inno Setup**（jrsoftware.org，免费）。

## 二、生成可执行程序（.exe）

**方式 A：双击**
直接双击 `build_win.bat`，等待约 1~3 分钟。

**方式 B：命令行**
```bat
cd /d D:\ZDQuote
python -m pip install -r requirements.txt
python build_win.py
```

产物：`dist\ZDQuote\ZDQuote.exe`（自包含，含 Python + Tcl/Tk + 全部插件，不依赖外部环境）。

> 双击 `ZDQuote.exe` 即可运行。如需分发给别人，把这个 `dist\ZDQuote\` 文件夹整体发过去就能用。

## 三、生成安装包（.exe 安装程序，推荐分发用）

1. 先用第二步生成 `dist\ZDQuote\`。
2. 用 **Inno Setup** 打开 `installer_win.iss`。
3. 菜单 `Build` → `Compile`（或按 `F9`）。
4. 产物：`installer\ZDQuote_Setup.exe` —— 双击即可像普通软件一样安装/卸载，自动建桌面图标。

> 若你的 Inno Setup 报找不到 `Chinese.isl`，打开 `installer_win.iss` 把 `[Languages]` 那段改成英文（脚本里已注释说明）。

## 四、数据在哪里

打包运行后，数据库与生成的报价单放在：

```
C:\Users\<你的用户名>\Documents\ZDQuote\
```

（这是为了避免写入只读的安装目录。要找报价单、转发微信，看这个文件夹即可。）

## 五、常见问题

- **双击 `ZDQuote.exe` 一闪而过 / 报错**：在文件夹地址栏输入 `cmd` 回车，再 `ZDQuote.exe` 看真实报错，把信息发我。
- **`python` 不是内部命令**：说明安装 Python 时没勾 `Add to PATH`，重装并勾选即可。
- **Windows 微信转发**：当前 Windows 版未集成自动发送，点"转发微信"会打开文件所在文件夹，请手动把文件拖入微信对话窗口。
- **杀软误报**：PyInstaller 打的包偶被 Windows Defender 误报，加白名单即可（这是打包工具的共性，非程序问题）。

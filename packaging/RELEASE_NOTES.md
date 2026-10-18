## SigWatermark 1.0.2

Portable builds for Windows x64, macOS Apple Silicon, macOS Intel, and Linux x64. Extract the complete archive before launching; no Python installation is needed. All four archives are covered by `SHA256SUMS.txt`.

### Windows startup fix

The Windows v1.0.0 archive accidentally included ICU DLLs from an unrelated Poppler installation on the build machine. QtCore expects the Windows ICU API, so those conflicting DLLs caused `DLL load failed while importing QtCore: The specified procedure could not be found`.

- Restrict Windows build-time DLL discovery to Python and Windows directories, preventing unrelated tools on PATH from contaminating the archive.
- Add a frozen GUI startup check in an isolated environment. It imports Qt, creates the actual application window, visits all six pages, runs the event loop, and requires an explicit success report. Windows checks use the native `windows` platform plugin.
- Add a source GUI startup regression test. The previous CLI-only check did not catch this failure because locale detection can fall back when QtCore is unavailable.

The watermark algorithm and stored data format are unchanged. Back up your existing data before upgrading and keep your original watermark password. Install this version in a fresh folder; do not merge its support files with an old archive.

### Downloads

| Platform | Archive |
| --- | --- |
| Windows x64 | `SigWatermark-1.0.2-windows-x64.zip` |
| macOS Apple Silicon | `SigWatermark-1.0.2-macos-arm64.zip` |
| macOS Intel | `SigWatermark-1.0.2-macos-x64.zip` |
| Linux x64 | `SigWatermark-1.0.2-linux-x64.tar.gz` |

Windows and macOS builds are unsigned; macOS builds are not notarized. English, Simplified Chinese, and Traditional Chinese documentation is included. The UI still follows your system language by default.

---

## 中文说明

修复 Windows v1.0.0 启动时报 `DLL load failed while importing QtCore` 的问题：原构建误打包了 Poppler 的 ICU DLL，与 Qt 所需的 Windows ICU 接口冲突。

本版本隔离 Windows 构建时的 DLL 搜索路径，并新增真正的图形界面启动验证：创建主窗口、检查六个页面、运行事件循环，要求明确成功报告；Windows 使用原生平台插件验证。四个平台通过测试、打包和图形界面启动检查后才发布。

请解压到全新目录，不要覆盖合并旧版 `_internal` 文件夹。升级前备份原有数据，保留水印密码，通过内置备份恢复迁移记录。水印算法和数据格式没有改变。

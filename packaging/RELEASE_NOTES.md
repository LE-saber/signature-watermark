## SigWatermark 1.0.1

Portable desktop app for invisible signature watermarks and document tracing.

### Downloads

| System | Archive |
| --- | --- |
| Windows x64 | `SigWatermark-1.0.1-windows-x64.zip` |
| macOS Apple Silicon | `SigWatermark-1.0.1-macos-arm64.zip` |
| macOS Intel | `SigWatermark-1.0.1-macos-x64.zip` |
| Linux x64 | `SigWatermark-1.0.1-linux-x64.tar.gz` |

Extract the complete archive before launching. Python is included. Keep the application and its support files together. `SHA256SUMS.txt` contains checksums for all four archives.

### Changes

- Publish native builds for Windows, macOS Apple Silicon, macOS Intel, and Linux.
- Replace the retired Intel macOS runner and update the Apple Silicon build environment.
- Make English the default repository README and portable quick-start guide, with complete Simplified and Traditional Chinese README versions.
- Include all three README versions in every archive and keep the macOS bundle version in sync with the application.
- Generate release checksums automatically after all platform tests and builds succeed.

### First launch

Open `SigWatermark.exe` on Windows, `SigWatermark.app` on macOS, or `SigWatermark/SigWatermark` on Linux. Set a watermark password of at least 12 characters in Settings. Retain the same password and signing records for later tracing; use the built-in backup feature when moving between computers.

The application UI supports nine languages and follows the system language by default. Changing the README default does not change the UI language preference. The watermark format remains `SIG-BLIND-WM-2`, with legacy extraction support.

Windows and macOS builds are unsigned; macOS builds are not notarized. Linux desktop installations may need the xcb runtime libraries listed in the README. Watermark recovery depends on image quality, alignment, and the background; this is not a cryptographic document-signing system.

---

## 中文说明

本版本提供 Windows x64、macOS Apple Silicon、macOS Intel 和 Linux x64 四种原生便携包，无需另行安装 Python。请完整解压后启动，并保留程序的配套文件。

仓库 README 和便携包快速说明默认使用英文，同时提供完整的简体中文、繁體中文 README。应用界面仍默认跟随系统语言，支持九种语言。首次使用请设置至少 12 个字符的水印密码，迁移电脑时请备份签发记录和密码。

四个平台的测试和构建全部通过后才自动发布，所有压缩包的校验值见 `SHA256SUMS.txt`。Windows、macOS 包尚未代码签名；macOS 包尚未公证。

## SigWatermark 1.0.4

Cleaner signature extraction, less intrusive translucent carriers, improved tracing over printed text and tinted paper, and generated watermark passwords.

### Changes

- Background removal now detects ruled/grid/form lines, edge clutter, shadows and paper texture, with rules intended to preserve crossing strokes, underlines and dots. Other handwriting still needs cropping out.
- The default carrier opacity is 24/255 (about 9%), down from 96/255; the slider minimum is 12. Tracing rebuilds carrier opacity, compensates for paper color, and searches for the recorded ink shape when text obscures the usual ink-region detection.
- Settings offers Generate and save on first launch, plus Generate and Copy. Passwords contain 24 random symbols in six groups separated by hyphens; user-entered passwords of at least 12 characters are still supported.
- The watermark format, embedding core and matching thresholds are unchanged (`SIG-BLIND-WM-2`).

### Validation and limits

Seven synthetic background cases retained 98.63–100% of known ink. Junk pixels in the ruled/grid cases fell from 56.75%/79.30% to 0.14%/0.37%. On three identical JPEG pages with a signature over text (white, cream and light blue), 1.0.3 did not match; 1.0.4 matched all three. These sample results are not a general recovery rate.

Processing speed varies: in a three-run comparison on a 2700×1140 plain-paper signature, median time increased from 0.981 s to 2.894 s because of the additional cleanup. See [validation methods, results and limits](https://github.com/LE-saber/signature-watermark/blob/v1.0.4/docs/VALIDATION.md).

Low-opacity signatures over printed text can yield only a possible match; results vary between watermark IDs and textures. This also occurred once on a synthetic white-paper page during release CI. Preserve output images and verify uncertain results against the original document.

### Upgrade

- Back up signing records, output PNGs and the original watermark password. Including the password in a backup requires encryption.
- Legacy settings with opacity 96 migrate to 24, including a manually chosen value of exactly 96; other values are retained. Set 96 again after upgrading if needed.
- Shape-based location needs the output PNG at its recorded path. Keep output images; direct watermark extraction can still be attempted without them.
- Extract the entire archive into a fresh directory and check the active data location in Settings. Changing storage mode does not move data automatically.

### Downloads

| Platform | Archive |
| --- | --- |
| Windows x64 | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-windows-x64.zip) |
| macOS Apple Silicon | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-macos-arm64.zip) |
| macOS Intel | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-macos-x64.zip) |
| Linux x64 | [tar.gz](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-linux-x64.tar.gz) |

No separate Python installation is needed. Archives include an English quick-start guide, English/Simplified Chinese/Traditional Chinese READMEs and validation notes. Verify with `SHA256SUMS.txt`. Windows and macOS builds are unsigned; macOS builds are not notarized.

---

## 中文说明

- **提取更干净：** 增加横格线、方格线、表格线、照片边缘杂物和纸面纹理清理，尽量保留交叉笔画、下划线和点。旁边的其他手写内容仍需先裁掉。
- **减少遮挡并改善溯源：** 默认载体不透明度从 96 降至 24/255（约 9%），滑块最低为 12；新增纸色补偿和签名压正文时的形状定位。
- **密码设置：** 首次启动可一键随机生成并保存，设置页增加随机生成和复制。生成密码包含 24 个随机字符，以连字符分组；也可自行输入至少 12 个字符的密码。
- **实测范围：** 七组合成去背景样本保留 98.63%～100% 的笔迹；三张白色、米黄、浅蓝纸的压正文 JPEG 对照图，旧版均未匹配，当前版均匹配。样本结果不代表通用恢复率。新增清理存在性能成本，不能保证所有图片更快，详细结果见验证文档。
- **升级注意：** 备份记录、输出图片和原密码；包含密码的备份必须加密。旧设置中的 96 会改为 24（手动选为 96 也会迁移），需要时可重新设回。形状定位依赖记录路径下的输出 PNG，请保留输出图片。完整解压后在设置中检查数据目录，切换存储模式不会自动搬移数据。

低不透明度签名压正文时仍可能只达到“可能匹配”，结果会随水印 ID 和纹理变化；发布测试中也观察到过这一情况。请保留输出图片，结果不确定时检查原文件。

水印格式仍为 `SIG-BLIND-WM-2`。英文、简体中文、繁体中文 README 和验证文档随包提供。

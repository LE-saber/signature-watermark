## SigWatermark 1.0.3

Turn signature photos/scans on white or light paper into electronic signatures with white, translucent, feathered, or textured feathered carriers, then embed a traceable invisible ID.

### Background processing fix

Previously, an opaque source image was placed over the selected carrier without removing its paper background. The original rectangle covered the translucent/feathered carrier, so changing the style did not produce the intended result.

- Integrate automatic paper-background removal directly into the desktop and CLI export pipelines; it is enabled by default.
- Normalize light-paper tint and gradual illumination changes, preserve colored ink, and remove paper-colored fringes around strokes.
- Preserve ink-only transparent PNGs while also detecting opaque paper regions inside PNGs with transparent corners.
- Add an automatic-removal checkbox and ink-retention threshold. Raise the threshold to retain faint ink, or disable removal to keep an original design.
- Use the same preparation for previews and actual exports. The top paper-color buttons change the preview scene only; the carrier style controls the output PNG.
- Create the requested padding around tightly cropped ink so feathered edges have space to fade.
- Requeue finished items when processing parameters change, allowing a new export without re-importing the image.
- Apply camera EXIF orientation before processing, store preparation parameters in signing records, and translate the new controls into all nine UI languages.

The watermark format remains `SIG-BLIND-WM-2`, and existing records/images remain traceable. Background processing uses the existing NumPy/Pillow dependencies; no cloud service or additional model download is required.

### Downloads

| Platform | Archive |
| --- | --- |
| Windows x64 | `SigWatermark-1.0.3-windows-x64.zip` |
| macOS Apple Silicon | `SigWatermark-1.0.3-macos-arm64.zip` |
| macOS Intel | `SigWatermark-1.0.3-macos-x64.zip` |
| Linux x64 | `SigWatermark-1.0.3-linux-x64.tar.gz` |

Extract the entire archive into a fresh directory. No separate Python installation is needed. Back up existing signing records and retain the watermark password when upgrading. All four archives are covered by `SHA256SUMS.txt`; Windows and macOS builds are unsigned, and macOS builds are not notarized.

Automatic removal is designed for a cropped signature on white/light paper. Ruled lines, other handwriting, and complex photographic backgrounds may require cropping or manual cleanup. Existing isolated frozen-GUI checks remain required on all four platforms before publication.

---

## 中文说明

修复“选了半透明或羽化样式，导出后仍保留原图背景”的问题。之前程序把带纸张背景的原图直接叠在载体上；现在默认先去除纸张背景、提取笔迹，再生成所选载体并嵌入水印，预览和实际导出共用同一流程。

- 白纸、浅色纸上的签名照片与扫描图可直接导入；透明笔迹 PNG 保留原样。
- 增加“自动去除原图背景”开关和“笔迹保留阈值”，淡笔迹可提高阈值。
- 真正补足笔迹周围的留白，让羽化边缘有空间过渡；修改处理参数后会把已完成图片重新加入队列。
- 自动校正相机方向、记录处理参数，新控件支持全部九种界面语言。
- 保留 Windows DLL 隔离构建和四平台图形界面启动检查。

请先裁切到签名区域。横格线、其他手写内容和复杂背景仍可能需要手动清理。升级请解压到新目录，通过备份恢复迁移数据，保留原水印密码；水印格式和旧图溯源兼容性不变。

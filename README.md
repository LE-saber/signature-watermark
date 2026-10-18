# SigWatermark

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

[![Build](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml/badge.svg)](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/LE-saber/signature-watermark)](https://github.com/LE-saber/signature-watermark/releases/latest)

A portable desktop app that turns signature photos into electronic signatures with translucent or feathered backgrounds, embeds invisible IDs, and traces signatures in PDF, Word documents, images, and scans.

Give each issued signature a separate ID and purpose, then check which issuance a signature came from when it appears in another document. Processing and signing records stay on your computer.

![Batch watermarking with a signature preview](docs/images/batch-watermark.png)

## Download

Choose a **portable application archive** from [Releases](https://github.com/LE-saber/signature-watermark/releases/latest). The automatically generated “Source code” downloads require a Python environment.

| Platform | Version 1.0.3 | Launch after extraction |
| --- | --- | --- |
| Windows x64 | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.3/SigWatermark-1.0.3-windows-x64.zip) | `SigWatermark/SigWatermark.exe` |
| macOS Apple Silicon | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.3/SigWatermark-1.0.3-macos-arm64.zip) | `SigWatermark.app` |
| macOS Intel | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.3/SigWatermark-1.0.3-macos-x64.zip) | `SigWatermark.app` |
| Linux x64 | [tar.gz](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.3/SigWatermark-1.0.3-linux-x64.tar.gz) | `./SigWatermark/SigWatermark` |

No separate Python installation is needed. Extract the entire archive and keep all support files together. Every archive includes an English quick-start guide and all three README versions. Verify downloads with [`SHA256SUMS.txt`](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.3/SHA256SUMS.txt).

Windows builds are unsigned. macOS builds are unsigned and not notarized; first launch may require approval in macOS security settings. Native macOS builds use macOS 15 runners. Linux builds use Ubuntu 22.04 and require a working desktop environment. On Debian/Ubuntu, install missing Qt/xcb runtime libraries with:

```bash
sudo apt-get install libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libdbus-1-3
```

## Quick start

1. Open the app and set a **watermark password of at least 12 characters** in Settings.
2. Add signature photos/scans on white or light paper, or a folder, in **Batch watermark**. **Remove original background automatically** is enabled by default. Ink-only transparent PNGs are preserved.
3. Choose a purpose and carrier style, preview the result, and generate watermarked PNGs. Raise **Ink retention threshold** for faint strokes, or turn off automatic removal to retain an original design. Each image receives a separate ID and signing record.
4. Use those PNGs in your documents. To investigate one later, open **Signature tracing** and add the PDF, Word document, image, or scan. Use manual region selection if automatic detection misses the signature.
5. Back up signing records and the watermark password before moving computers or cleaning files.

The README defaults to English. The application UI follows the system language and supports English, Simplified Chinese, Traditional Chinese, Japanese, Korean, French, Spanish, Russian, and Arabic. Change it in Settings and restart; Arabic uses right-to-left layout.

## Features

- Batch processing, file/folder drag and drop, purpose labels, custom output names, previews, and optional read-back self-checks.
- Integrated paper-background removal, light-paper/shadow normalization, adjustable ink retention, and camera orientation handling.
- Four replacement carriers: white, translucent, feathered, and feathered with subtle texture. Changing processing settings puts finished items back in the queue for a new export.
- Tracing from PDF embedded images, Word `.docx`/`.docm` media, image files, photos, and scans, with size restoration and manual region selection.
- Searchable local signing records with timestamps, source/output SHA-256 hashes, image geometry, and CSV export.
- Selective `.swbak` backup/restore, optional AES-256 encryption, backup history, and reminders.
- Storage usage and cleanup, including an option to delete only backed-up files while retaining signing records.
- Desktop GUI and command-line entry points; the main app requires no server.

## How it works

Paper is removed before carrier generation. Preview and export use the same preparation; tight crops receive the requested padding around their ink. The paper-color buttons at the top change the preview scene only; the carrier styles determine the exported PNG.

Each issued image carries a short ID such as `W1234ABC`, encoded as 63 watermark bits. The purpose and other metadata live in SQLite and are looked up by ID.

The bundled core adapts `blind_watermark 0.4.4` using NumPy: YUV conversion → Haar DWT → 4×4 low-frequency blocks → DCT → password-seeded coefficient shuffling → SVD quantization. Bits repeat across blocks and channels. Extraction reverses the shuffling and aggregates observations without needing the original image.

The current `SIG-BLIND-WM-2` format embeds into the image's appearance on white paper, then reconstructs RGB values while preserving alpha. This reduces signal loss when semi-transparent PNGs are placed in a document. Extraction also tries raw RGB for legacy marks.

For scans, ink-region detection and the stored signature bounding box help reconstruct the carrier. Matching uses the 49 variable positions in the encoding: at least 46 agreeing positions yields a match; 43–45 can yield a possible match if clearly ahead of other records. These thresholds are not accuracy percentages.

## Data and passwords

Portable mode uses `data/` next to the executable. If that location is not writable, the app uses the platform's user data directory. Settings shows the active location. Changing storage mode takes effect on restart and does not automatically move existing data.

| Data | Storage |
| --- | --- |
| Settings | `settings.json` |
| Signing records and tracked files | `records.sqlite` |
| Source image copies | `uploads/` |
| Watermarked images | `out/` by default; customizable |
| Documents imported through the tracing GUI | `docs/` |
| Cache / backups | `cache/` / `backup/` |

The watermark password is stored in the OS keyring when available, otherwise in `settings.json`. Keep the data directory private. Including the watermark password in a backup requires encryption. Retain the original password and records: changing the password does not re-embed previously issued images, and an ID alone cannot recover its purpose or signing history.

## Command line

Configure the password in the GUI first. Windows PowerShell examples, from the extracted archive directory:

```powershell
.\SigWatermark\SigWatermark.exe embed .\signatures --purpose "Contract A" --mode feathered_texture
.\SigWatermark\SigWatermark.exe trace .\contract.pdf .\document.docx .\scan.jpg
.\SigWatermark\SigWatermark.exe --data-dir .\alternate-data embed .\signature.png --out .\output
```

For startup diagnostics, run the executable with `--gui-smoke-test <empty-folder>`; it writes `gui-smoke.json` and exits after checking all six pages.

For faint ink, add `--background-threshold 245`. Use `--no-remove-background` to preserve an original background, or `--remove-background` to explicitly enable removal.

On Linux, use `./SigWatermark/SigWatermark`; on macOS, use `./SigWatermark.app/Contents/MacOS/SigWatermark` with the same arguments. `--data-dir` must precede the subcommand. Available modes: `white`, `translucent`, `feathered`, `feathered_texture`.

## Limitations

- Automatic background removal is designed for cropped signatures on white/light paper. Crop to the signature first; ruled lines, other handwriting, or complex photographic backgrounds may need manual cleanup with the separate `tools/signature-remove-bg/` tool.

- Recovery depends on signal and alignment. Heavy compression, severe resizing, cropping, rotation, perspective changes, or low-quality printing/scanning may prevent a match. Some sample tests recover at 50% size after restoration; this is not a general guarantee.
- Semi-transparent carriers are intended for white or light backgrounds. Photo tracing does not perform perspective correction.
- Automatic PDF tracing primarily examines embedded images; it does not scan every rendered page as a fallback. Word results enumerate embedded images rather than actual page numbers. Older `.doc` files are unsupported.
- A watermark supports issuance tracing. It does not prevent copying, authenticate the signer, or protect the complete document from modification.
- Automated robustness checks cover white-background compositing, 75%/50% resizing with size restoration, and JPEG quality 90 on the supplied fixture, rather than a universal recovery rate.

## Development

CI uses Python 3.12. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps blind-watermark==0.4.4
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe packaging/build.py
```

On macOS/Linux, create the environment with `python3 -m venv .venv`, then use `.venv/bin/python` for the same commands. Linux needs the Qt libraries listed above and `binutils` for packaging.

PyInstaller builds only for the current OS/architecture. `packaging/build.py` recreates `build/` and `dist/`; archives appear in `dist/`. Tag pushes matching `v*` run native tests, builds, and isolated frozen GUI startup checks for all four targets, then generate checksums and publish after every check succeeds.

UI translations are maintained in `tools/i18n/table*.py`. After changing UI strings, update translations and run `python tools/i18n/build.py`; the script and tests check coverage and placeholders.

## Source layout

| Path | Responsibility |
| --- | --- |
| `app.py` | GUI/CLI entry point |
| `sigwm/background.py` | Paper-background removal using NumPy and Pillow |
| `sigwm/core.py`, `sigwm/vendor/bwm/` | Carriers, embedding, extraction, robustness checks |
| `sigwm/imgops.py`, `sigwm/trace.py` | Image operations, document parsing, detection, matching |
| `sigwm/service.py`, `sigwm/storage.py` | Batch processing, settings, SQLite, tracked files |
| `sigwm/backup.py`, `sigwm/secret.py` | Backup/restore and password storage |
| `sigwm/gui/`, `sigwm/i18n.py`, `sigwm/locales/` | Desktop interface and localization |
| `packaging/`, `.github/workflows/build.yml` | Native portable builds and releases |
| `tests/` | Core, tracing, data, image-operation, and translation tests |
| `tools/signature-remove-bg/` | Separate background-removal web tool with its own dependencies |

Legacy Python, batch, PowerShell, and OpenStego files are retained. Import old signing records through Settings. Legacy records lack the bounding box needed for automatic on-page localization.

## Third-party notices

The watermark core is adapted from [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) under MIT; see `sigwm/vendor/bwm/LICENSE`. Bundled Inter, IBM Plex Mono, and Noto fonts use SIL OFL; notices accompany the fonts and portable archives. macOS uses installed system UI fonts. The separate background-removal tool includes its own license and dependency documentation.

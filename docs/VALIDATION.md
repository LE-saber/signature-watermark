# 1.0.4 validation and known limits

[English README](../README.md) · [简体中文](../README.zh-CN.md) · [繁體中文](../README.zh-TW.md)

These checks compare tag `v1.0.3` (`d634b21`) with the 1.0.4 source on Windows, Python 3.13.1. They describe the tested samples, not a general recovery rate. Release CI separately tests Python 3.12 on all four target platforms.

## Background removal

`tests/hard_backgrounds.py` generates seven 900×380 images with a known handwriting mask, including JPEG artifacts. Both versions received exactly the same inputs at the default ink threshold of 220.

“Junk” is the fraction of retained output pixels outside a small neighborhood of the true ink; `score()` allows a two-pixel edge tolerance. “Ink retained” measures the fraction of ground-truth ink pixels kept above alpha 128.

| Sample | 1.0.3 junk | 1.0.4 junk | 1.0.4 ink retained |
| --- | ---: | ---: | ---: |
| Plain paper | 0.00% | 0.00% | 100.00% |
| Ruled paper | 56.75% | 0.14% | 100.00% |
| Grid paper | 79.30% | 0.37% | 100.00% |
| Form border | 56.21% | 0.00% | 100.00% |
| Black ink crossing a form line | 41.35% | 0.00% | 98.63% |
| Desk at the photo edge | 68.53% | 0.00% | 100.00% |
| Textured/recycled paper | 18.66% | 0.17% | 100.00% |

Additional tests check a signature underline, dots, tilted rules, existing transparent ink, faint strokes, camera orientation, and carrier alpha after export. Real photos may still need cropping or manual cleanup, especially when other handwriting is present.

## Tracing over printed text

A single signature from `tests/fixtures/signature.png` was issued with opacity 24/255, pasted over printed text on 1700×2200 white, cream and light-blue pages, and saved as JPEG quality 85. Both versions analyzed the same three images and the same signing record.

| Paper | 1.0.3 | 1.0.4 |
| --- | --- | --- |
| White | No match | Match, 61/63 agreeing bits |
| Cream | No match | Match, 63/63 agreeing bits |
| Light blue | No match | Match, 63/63 agreeing bits |

Watermark IDs and carrier textures vary between issuances. A low-opacity signature over printed text can yield only a possible match, including on a synthetic white-paper page observed during release CI. The table above describes one controlled comparison, not every possible issued image.

Bit agreement is not a confidence percentage. The unchanged classifier uses the 49 variable encoding positions. `tests/test_trace.py` also checks unrelated IDs and resized signatures. Shape-based location needs the issued output PNG at the stored path; deleting that image removes this fallback, while direct watermark extraction can still be attempted.

## Performance

Downsampling the lighting estimate reduces one cost, but line/component cleanup adds others. Processing is not uniformly faster. On a 2700×1140 enlargement of the plain-paper sample, three sequential runs per version had median times of **0.981 s for 1.0.3** and **2.894 s for 1.0.4**, with `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`. Hardware, image content and dimensions change these timings. No universal speed-up is claimed.

## Running checks

Install the development dependencies as described in the README, then run:

```sh
python -m pytest -q tests
```

Focused checks are `tests/test_background.py`, `tests/test_trace.py`, `tests/test_data.py` and `tests/test_i18n.py`. CI also builds each portable archive and starts all six frozen GUI pages in an isolated environment. Windows startup uses the native Windows Qt platform; Linux and macOS smoke checks use offscreen rendering. These checks do not substitute for testing every interactive workflow on every operating system.

## Upgrade behavior

- The watermark format remains `SIG-BLIND-WM-2`; retain existing records and the original watermark password.
- Older settings without `settings_version: 2` change opacity 96 to 24. The migration cannot distinguish the former default from a user-selected value of exactly 96; set it back after upgrading if needed. Other opacity values are retained.
- Keep output PNGs if you want shape-based location. Back up records, outputs and the watermark password before cleanup or migration; password backups require encryption.
- Printing, heavy compression, cropping, rotation and perspective distortion can prevent recovery. Automatic photo perspective correction and a general fallback scan of every rendered PDF page are not implemented.

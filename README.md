# SigWatermark

給簽名圖片加隱形水印的桌面工具：批量加水印、從文件/照片/掃描件溯源、簽發記錄、備份恢復、清理空間。
Windows、macOS、Linux 各有一個便攜壓縮包，解壓後雙擊即可使用（見 `packaging/build.py` 生成的 `使用說明.txt`）。

## 目錄

| 路徑 | 內容 |
|---|---|
| `app.py` | 入口：無參數開窗口；`embed` / `trace` 子命令走命令行 |
| `sigwm/core.py` | 載體生成、嵌入、提取、魯棒性自測 |
| `sigwm/vendor/bwm/` | blind_watermark 0.4.4 的核心算法（MIT），numpy 重寫並鎖定版本 |
| `sigwm/imgops.py` | 取代 OpenCV 的幾個圖像運算（顏色轉換、縮放、形態學、連通域） |
| `sigwm/trace.py` | PDF / Word / 圖片溯源：嵌入圖片直接提取，整頁圖片先定位簽名 |
| `sigwm/storage.py` | 資料目錄（便攜 / 使用者目錄）、SQLite 記錄、文件追蹤 |
| `sigwm/backup.py` | `.swbak` 選擇性備份與恢復（可 AES-256 加密） |
| `sigwm/secret.py` | 水印密碼：系統鑰匙串，沒有時退回資料目錄 |
| `sigwm/gui/` | PySide6 界面，按 HTML 原型實現 |
| `sigwm/i18n.py`、`sigwm/locales/` | 界面翻譯：繁中（原文）、简中、English、日本語、한국어、Français、Español、Русский、العربية |
| `sigwm/fonts/`、`sigwm/gui/fonts.py` | 隨程序附帶的字體和按平台、按語言選字體的邏輯 |
| `tools/i18n/` | 翻譯總表（每行原文 + 8 種譯文）和生成 `locales/*.json` 的腳本 |
| `packaging/` | PyInstaller spec、打包腳本、圖標 |
| `.github/workflows/build.yml` | 三平台構建（Win x64、macOS arm64/Intel、Linux x64），打 `v*` 標籤時發佈 |

舊版的 `signature_watermark_blind.py`、`.bat` 和 OpenStego 腳本保留未動；新程序可以在「設定」裏導入舊版記錄。

## 開發

```bash
python3 -m venv .venv-linux
.venv-linux/bin/pip install -r requirements-dev.txt
.venv-linux/bin/pip install --no-deps blind-watermark==0.4.4
.venv-linux/bin/python -m pytest -q tests
.venv-linux/bin/python app.py
```

打包（只能打當前系統的包）：`python packaging/build.py`，產物在 `dist/`。Linux 需要 `binutils`。

## 字體與語言

- macOS 用系統界面字體（SF Pro + 蘋方 / Hiragino / Apple SD Gothic）。SF Pro 不允許隨程序分發，所以只調用系統自帶的那份。
- Windows、Linux 用附帶的 Inter（OFL，最接近 SF Pro 的開源字體）；中日韓字用系統字體（微軟正黑/雅黑、Yu Gothic、Malgun Gothic；Linux 用 Noto Sans CJK，Linux 包裏另附一份）。
- 漢字按界面語言選字形：日文界面用日文字形，简中用大陸字形。阿拉伯文用附帶的 Noto Sans Arabic，界面自動改為從右到左。
- 語言默認跟隨系統，可在「設定 → 界面語言」切換，重新啟動後生效。

改了界面文字或新增 `tr("…")` 之後：在 `tools/i18n/table*.py` 補上譯文，再執行

```bash
.venv-linux/bin/python tools/i18n/build.py
```

腳本會檢查每條字符串都有譯文、佔位符一致；`tests/test_i18n.py` 也會檢查。

## 和舊腳本相比的變化

- **在外觀上嵌入**：舊腳本把水印嵌在半透明載體的原始 RGB 上，PNG 疊到文件上後信號被透明度削弱，「合成到白底」基本提取不出來。現在先算出載體疊在白紙上的樣子，在那上面嵌入，再反推半透明像素。四種模式都能扛住合成白底、縮小到 50%、JPEG 75。新圖格式記為 `SIG-BLIND-WM-2`；舊圖仍可提取。
- **白底模式底色 250**：純白 255 會被截斷導致翻位（原版算法自己的回提也會錯）。
- **溯源判定**：63 位裏有 14 位是所有 ID 共有的格式位，只用其餘 49 位區分記錄；≥46 判匹配，43–45 且明顯領先其他記錄判「可能匹配」。閾值用「別人的乾淨水印」校準，測試裏沒有誤報。

## 已知限制

- 簽名縮到原尺寸約 60% 以下、或經過強壓縮後，水印信號不足，只能給出「可能匹配」或找不到。
- 照片沒有做透視校正，請盡量正面拍攝；可以在溯源頁手動框選簽名。
- 半透明載體只在白色或淺色紙上可靠。
- macOS 包未簽名公證，第一次需右鍵「打開」；Windows 未做代碼簽名，可能出現 SmartScreen 提示。

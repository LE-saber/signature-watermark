# SigWatermark

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文**

[![建置](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml/badge.svg)](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml)
[![版本](https://img.shields.io/github/v/release/LE-saber/signature-watermark)](https://github.com/LE-saber/signature-watermark/releases/latest)

為簽名圖片嵌入隱形 ID，並從 PDF、Word、圖片與掃描件追查簽發記錄的便攜桌面工具。

每次簽發使用不同的 ID 與用途，日後發現簽名出現在其他文件中，就可以嘗試追查對應的簽發記錄。主程式的影像處理與記錄保存在本機。

![批量加水印與簽名預覽](docs/images/batch-watermark.png)

## 下載

從 [Releases](https://github.com/LE-saber/signature-watermark/releases/latest) 下載**便攜應用程式壓縮包**。GitHub 自動產生的 “Source code” 是原始碼，需要自行設定 Python 環境。

| 平台 | 1.0.1 版本 | 解壓後啟動 |
| --- | --- | --- |
| Windows x64 | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.1/SigWatermark-1.0.1-windows-x64.zip) | `SigWatermark/SigWatermark.exe` |
| macOS Apple Silicon | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.1/SigWatermark-1.0.1-macos-arm64.zip) | `SigWatermark.app` |
| macOS Intel | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.1/SigWatermark-1.0.1-macos-x64.zip) | `SigWatermark.app` |
| Linux x64 | [tar.gz](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.1/SigWatermark-1.0.1-linux-x64.tar.gz) | `./SigWatermark/SigWatermark` |

無需另外安裝 Python。請完整解壓，保留程式與配套檔案。每個壓縮包均附帶英文快速說明及三種語言的 README。校驗值見 [`SHA256SUMS.txt`](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.1/SHA256SUMS.txt)。

Windows 包未進行程式碼簽署；macOS 包未簽署、公證，首次啟動可能需要在系統安全性設定中核准。macOS 包在 macOS 15 原生環境建置。Linux 包在 Ubuntu 22.04 建置，需要桌面環境。Debian/Ubuntu 如缺少 Qt/xcb 執行階段函式庫，可安裝：

```bash
sudo apt-get install libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libdbus-1-3
```

## 快速開始

1. 開啟程式，在「設定」中設定**至少 12 個字元的水印密碼**。
2. 在「批量加水印」中加入圖片或資料夾，建議使用透明底 PNG。照片或掃描件可先用獨立的 `tools/signature-remove-bg/` 工具去背景。
3. 填寫用途、選擇載體樣式、預覽並產生水印 PNG。每張圖片都有獨立 ID 與簽發記錄。
4. 將產生的 PNG 用於文件。日後在「簽名溯源」中加入 PDF、Word、圖片或掃描件進行查詢；自動偵測不準時可手動框選簽名區域。
5. 更換電腦或清理檔案前，備份簽發記錄與水印密碼。

儲存庫 README 預設為英文。程式介面預設跟隨系統語言，支援英文、簡體中文、繁體中文、日文、韓文、法文、西班牙文、俄文與阿拉伯文。在設定中切換語言，重新啟動後生效；阿拉伯文採用由右至左的版面。

## 功能

- 批量處理、拖入檔案或資料夾、用途標籤、自訂輸出名稱、預覽及可選的回提自檢。
- 四種載體：白底、半透明、羽化、羽化加淡紋理。
- 從 PDF 內嵌圖片、Word `.docx`/`.docm` 媒體圖片、一般圖片、照片及掃描件溯源，支援尺寸還原與手動選區。
- 本機簽發記錄搜尋、時間記錄、來源與輸出檔案的 SHA-256、影像幾何資訊及 CSV 匯出。
- `.swbak` 選擇性備份與還原、可選 AES-256 加密、備份歷史及提醒。
- 空間統計與清理，可只刪除已備份檔案，保留簽發記錄。
- 圖形介面與命令列；主程式無需伺服器。

## 實作原理

圖片只攜帶類似 `W1234ABC` 的短 ID，編碼後為 63 位水印。用途等完整資訊保存在 SQLite，透過 ID 關聯查詢。

內附核心以 NumPy 改寫 `blind_watermark 0.4.4`：YUV 轉換 → Haar 小波轉換 → 低頻部分分為 4×4 小區塊 → DCT → 密碼派生的係數重排 → SVD 量化。位元在多個區塊與通道中重複寫入；提取時解除重排並彙整結果，不需要原始無水印圖片。

目前格式為 `SIG-BLIND-WM-2`。新版先在「合成至白紙上的顯示效果」中嵌入，再反算 RGB 並保留透明通道，減輕半透明圖片疊入文件後水印變弱的問題。提取時也嘗試原始 RGB，以相容舊圖。

掃描圖先偵測墨跡區域，再結合記錄中的簽名邊界還原載體。63 位編碼中有 49 個位置能區分不同 ID：至少 46 位一致判為匹配；43–45 位一致且明顯領先其他記錄時可判為可能匹配。這些門檻不是準確率。

## 資料與密碼

預設在程式旁的 `data/` 保存資料；目錄無法寫入時使用系統使用者資料目錄。實際位置見設定。切換儲存模式在重新啟動後生效，不會自動搬移原資料。

| 內容 | 儲存位置 |
| --- | --- |
| 設定 | `settings.json` |
| 簽發記錄、檔案追蹤 | `records.sqlite` |
| 原圖副本 | `uploads/` |
| 水印圖片 | 預設 `out/`，可修改 |
| 透過溯源介面匯入的文件 | `docs/` |
| 快取、備份 | `cache/`、`backup/` |

密碼優先存入系統鑰匙串；不可用時退回 `settings.json`，請妥善保管資料目錄。備份包含水印密碼時，必須啟用加密。應保留原密碼與記錄：更換密碼不會重新處理舊圖片，只有 ID 也無法還原用途與簽發歷史。

## 命令列

先在圖形介面設定密碼。在解壓目錄開啟 Windows PowerShell：

```powershell
.\SigWatermark\SigWatermark.exe embed .\signatures --purpose "合約 A" --mode feathered_texture
.\SigWatermark\SigWatermark.exe trace .\contract.pdf .\document.docx .\scan.jpg
.\SigWatermark\SigWatermark.exe --data-dir .\alternate-data embed .\signature.png --out .\output
```

Linux 使用 `./SigWatermark/SigWatermark`，macOS 使用 `./SigWatermark.app/Contents/MacOS/SigWatermark`，參數相同。`--data-dir` 必須放在子命令之前。模式可選 `white`、`translucent`、`feathered`、`feathered_texture`。

## 使用限制

- 還原取決於水印訊號與對齊。強壓縮、大幅縮放、裁剪、旋轉、透視變形及低品質列印掃描都可能導致失敗。部分樣本縮小到 50% 後還原尺寸仍能提取，不代表所有圖片都能達到相同效果。
- 半透明載體適合白色或淺色背景；照片溯源未做透視校正。
- 自動 PDF 分析主要檢查內嵌圖片，沒有對所有渲染頁進行後備掃描。Word 結果按媒體圖片編號，並非實際頁碼；不支援舊 `.doc` 格式。
- 水印用於簽發溯源，不能阻止複製、驗證簽署人身分或保證整份文件未被修改。
- 自動魯棒性檢查針對內附樣本，涵蓋合成白底、縮小至 75%/50% 後還原尺寸、JPEG 品質 90，不能據此推算通用還原率。

## 開發

CI 使用 Python 3.12。Windows：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps blind-watermark==0.4.4
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe packaging/build.py
```

macOS/Linux 用 `python3 -m venv .venv` 建立環境，再以 `.venv/bin/python` 執行相同命令。Linux 打包需要前述 Qt 函式庫及 `binutils`。

PyInstaller 只能建置目前系統與架構。`packaging/build.py` 會重建 `build/` 與 `dist/`，壓縮包輸出至 `dist/`。推送 `v*` 標籤後，自動執行四種目標平台的原生測試與建置，全部成功後產生校驗值並發布 Release。

介面翻譯維護於 `tools/i18n/table*.py`。修改介面文字後補充譯文，再執行 `python tools/i18n/build.py`；腳本與測試會檢查譯文覆蓋及預留位置。

## 原始碼結構

| 路徑 | 職責 |
| --- | --- |
| `app.py` | 圖形介面、命令列入口 |
| `sigwm/core.py`、`sigwm/vendor/bwm/` | 載體、嵌入、提取、魯棒性檢查 |
| `sigwm/imgops.py`、`sigwm/trace.py` | 影像運算、文件解析、定位及匹配 |
| `sigwm/service.py`、`sigwm/storage.py` | 批量處理、設定、SQLite 及檔案追蹤 |
| `sigwm/backup.py`、`sigwm/secret.py` | 備份還原及密碼保存 |
| `sigwm/gui/`、`sigwm/i18n.py`、`sigwm/locales/` | 桌面介面、多語言 |
| `packaging/`、`.github/workflows/build.yml` | 原生便攜包及版本發布 |
| `tests/` | 核心、溯源、資料、影像運算及翻譯測試 |
| `tools/signature-remove-bg/` | 獨立去背景 Web 工具，需另行安裝依賴 |

舊版 Python、批次檔、PowerShell 及 OpenStego 檔案均保留，可在設定中匯入舊簽發記錄。舊記錄沒有簽名邊界，不能用於自動頁面定位。

## 第三方元件

水印核心改寫自 [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark)，採用 MIT 授權，全文見 `sigwm/vendor/bwm/LICENSE`。內附的 Inter、IBM Plex Mono 與 Noto 字體採用 SIL OFL，授權隨字體及便攜包提供。macOS 呼叫系統既有介面字體。獨立去背景工具附帶自己的授權及依賴說明。

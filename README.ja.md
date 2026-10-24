# SigWatermark

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](https://github.com/LE-saber/signature-watermark/blob/main/README.ja.md)

[![Build](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml/badge.svg)](https://github.com/LE-saber/signature-watermark/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/LE-saber/signature-watermark)](https://github.com/LE-saber/signature-watermark/releases/latest)

署名写真から、半透明またはぼかした背景の電子署名画像を作成し、目に見えない ID を埋め込むポータブルデスクトップアプリです。PDF、Word 文書、画像、スキャンに含まれる署名が、どの発行記録に由来するかを調べます。

発行ごとに別の ID と用途を付け、別文書に現れた署名を照合できます。処理と署名記録は利用者のコンピューター内に保持します。

![署名プレビュー付きの一括透かし処理](docs/images/batch-watermark.png)

## 1.0.4 の変更

- 罫線、方眼、フォームの線、写真端の不要物、紙の模様を除去し、交差する筆画、下線、点の保持を図ります。
- 透かしを載せる背景の既定不透明度を 96 から 24/255（約 9%）へ変更。追跡時に紙色を補正し、印刷文字と接する署名を探索します。
- 初回にランダムな透かしパスワードを生成・保存でき、設定にも生成とコピーを追加。
- 形式は `SIG-BLIND-WM-2` のまま。既存画像には元のパスワードと記録が必要です。

![初回のパスワード設定](docs/images/password-setup.png)

更新前に記録、出力画像、パスワードをバックアップしてください。古い設定の不透明度 96 は、手動で 96 にしていた場合も 24 へ移行します。他の値は保持します。形状による位置検出には記録されたパスの出力 PNG が必要なので、データ整理時も保持してください。性能上の代償を含む[検証結果と限界](docs/VALIDATION.md)を参照してください。

## ダウンロード

[Releases](https://github.com/LE-saber/signature-watermark/releases/latest) で**ポータブルアプリのアーカイブ**を選びます。自動生成の「Source code」は Python 環境が必要です。

| 環境 | 1.0.4 | 展開後の起動先 |
| --- | --- | --- |
| Windows x64 | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-windows-x64.zip) | `SigWatermark/SigWatermark.exe` |
| macOS Apple Silicon | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-macos-arm64.zip) | `SigWatermark.app` |
| macOS Intel | [ZIP](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-macos-x64.zip) | `SigWatermark.app` |
| Linux x64 | [tar.gz](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SigWatermark-1.0.4-linux-x64.tar.gz) | `./SigWatermark/SigWatermark` |

Python の別途インストールは不要です。アーカイブをすべて展開し、関連ファイルを一緒に保持します。既存 v1.0.4 アーカイブには英語のクイックガイドと英語/簡体字中国語/繁体字中国語 README が入っています。この日本語ガイドはオンライン文書で、文書更新によるアーカイブの再ビルドは行っていません。[SHA256SUMS.txt](https://github.com/LE-saber/signature-watermark/releases/download/v1.0.4/SHA256SUMS.txt) で取得物を照合してください。

Windows と macOS のビルドは署名なしで、macOS は公証もありません。macOS の初回起動ではセキュリティ設定で許可が必要な場合があります。macOS ビルドは macOS 15 runner、Linux は Ubuntu 22.04 を使います。Linux にはデスクトップ環境が必要です。Debian/Ubuntu で Qt/xcb ライブラリーが不足する場合：

```bash
sudo apt-get install libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libdbus-1-3
```

## クイックスタート

1. 設定で透かしパスワードを指定します。**Generate and save** で生成するか、**12 文字以上**を入力します。
2. **Batch watermark** へ白/薄色の紙の署名写真・スキャン、またはフォルダーを追加します。原背景の自動除去は既定で有効です。筆跡だけの透過 PNG は保持されます。
3. 用途と背景スタイルを選び、プレビュー後に透かし入り PNG を生成します。薄い筆跡には保持しきい値を上げ、元の意匠を残す場合は背景除去を無効にします。各画像に個別 ID と記録を作成します。
4. PNG を文書へ挿入します。後日調べる際は **Signature tracing** へ PDF、Word、画像、スキャンを追加します。自動検出で見つからなければ手動で領域を選びます。
5. PC 移行や整理の前に署名記録と透かしパスワードをバックアップします。

README の既定は英語です。UI はシステム言語に従い、英語、簡体字中国語、繁体字中国語、日本語、韓国語、フランス語、スペイン語、ロシア語、アラビア語に対応します。設定で変更後に再起動します。アラビア語は右から左の配置です。

## 機能

- 一括処理、ファイル/フォルダーのドラッグ＆ドロップ、用途ラベル、出力名、プレビュー、任意の読戻し確認。
- 紙背景除去、薄い紙色/影の補正、筆跡保持しきい値、カメラの向きへの対応。
- 白、半透明、ぼかし、微細模様付きぼかしの 4 スタイル。設定変更時は完了画像を再処理のキューへ戻します。既定 24/255 の薄い背景で下の文字を読みやすくし、追跡時は色紙や本文と接する署名を補正・探索します。
- PDF 埋め込み画像、Word `.docx` / `.docm` 内メディア、写真、スキャン等の追跡。サイズ復元と手動領域選択。
- 時刻、入出力 SHA-256、画像形状を記録するローカル台帳と CSV 出力。
- 選択式 `.swbak` バックアップ/復元、任意の AES-256 暗号化、履歴、通知。
- 使用容量確認と整理。記録を残してバックアップ済みファイルだけを削除する選択肢。
- GUI と CLI。主アプリにサーバーは不要です。

## 仕組み

背景を生成する前に紙を除去します。プレビューと出力は同じ前処理を使い、きつく切り抜いた筆跡にも指定余白を足します。上部の紙色ボタンはプレビューの場面だけを変更し、背景スタイルが出力 PNG を決めます。

画像には `W1234ABC` のような短い ID を 63 ビットで埋め込みます。用途などの情報は SQLite に保存し、ID から参照します。

同梱コアは `blind_watermark 0.4.4` を NumPy で適応したものです。YUV 変換 → Haar DWT → 4×4 低周波ブロック → DCT → パスワード由来の係数並べ替え → SVD 量子化を行い、ブロック/チャンネルへビットを反復します。抽出は並べ替えを戻し、観測を集約するため、元画像そのものは不要です。

`SIG-BLIND-WM-2` は白紙上で見える外観に埋め込み、その後 alpha を保ちながら RGB を再構成します。半透明 PNG を文書に配置する際の信号損失を抑える目的です。旧形式には raw RGB 抽出も試みます。

スキャンでは筆跡領域検出と記録の境界ボックスから背景を復元します。判定は符号の 49 可変位置を比較し、46 以上の一致を match、43–45 で他記録より十分優位なら possible match とします。**このしきい値は正解率の百分率ではありません。**

## データとパスワード

ポータブルモードは実行ファイル横の `data/` を使います。書込不能なら OS のユーザーデータ領域へ移ります。現在の場所は設定に表示します。保存モードの変更は再起動後に有効となり、既存データを自動移動しません。

| データ | 保存先 |
| --- | --- |
| 設定 | `settings.json` |
| 発行記録と追跡ファイル | `records.sqlite` |
| 元画像のコピー | `uploads/` |
| 透かし入り画像 | 既定 `out/`、変更可能 |
| 追跡 GUI で取り込んだ文書 | `docs/` |
| キャッシュ / バックアップ | `cache/` / `backup/` |

パスワードは利用可能なら OS キーリング、そうでなければ `settings.json` に保存します。データディレクトリを非公開に保ってください。パスワードを含むバックアップには暗号化が必要です。元のパスワードと記録を保持してください。変更しても発行済み画像は再埋込されず、ID だけでは用途や履歴を復元できません。

## コマンドライン

先に GUI でパスワードを設定します。展開先での Windows PowerShell 例：

```powershell
.\SigWatermark\SigWatermark.exe embed .\signatures --purpose "Contract A" --mode feathered_texture
.\SigWatermark\SigWatermark.exe trace .\contract.pdf .\document.docx .\scan.jpg
.\SigWatermark\SigWatermark.exe --data-dir .\alternate-data embed .\signature.png --out .\output
```

起動診断は `--gui-smoke-test <empty-folder>` を指定します。6 ページを確認して `gui-smoke.json` を書き、終了します。

薄い筆跡には `--background-threshold 245`、元背景を保持するには `--no-remove-background`、明示的に除去するには `--remove-background` を指定します。

Linux は `./SigWatermark/SigWatermark`、macOS は `./SigWatermark.app/Contents/MacOS/SigWatermark` で同じ引数を使えます。`--data-dir` はサブコマンドより前に置きます。モードは `white`、`translucent`、`feathered`、`feathered_texture` です。

## 制約

- 紙上の署名を切り抜いた画像向けです。罫線、方眼、フォーム線、交差線、机の端、影、むら、紙の模様を処理しますが、難しい画像は手作業が必要です。隣の別の手書き文字は除けないため先に切り取ってください。
- 本文上の低不透明度署名は possible match に留まる場合があり、ID や模様によって結果が変わります。出力画像を保持し、不確かな場合は元文書で確認してください。
- 強い圧縮、極端なサイズ変更、切抜、回転、遠近変形、低品質の印刷/スキャンでは照合できない場合があります。50% 縮小から復元できる試験例も、一般的な保証ではありません。
- 半透明背景は白/薄色の背景を想定します。写真の遠近補正はありません。
- 自動 PDF 追跡は主に埋め込み画像を調べ、全ページ描画の一律フォールバックはしません。Word の結果番号は画像の列挙で、実ページ番号ではありません。旧 `.doc` は非対応です。
- 透かしは発行元の追跡を助けますが、コピー防止、署名者認証、文書全体の改変防止ではありません。
- 自動耐性試験は提供画像の白背景合成、75%/50% 縮小とサイズ復元、JPEG 品質 90 等で、普遍的な復元率を示しません。

## 開発

CI は Python 3.12 を使います。Windows での手順：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps blind-watermark==0.4.4
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe packaging/build.py
```

macOS/Linux は `python3 -m venv .venv` 後、同じ操作に `.venv/bin/python` を使います。Linux は上記 Qt ライブラリーと、パッケージ作成用 `binutils` が必要です。

PyInstaller は実行 OS/アーキテクチャ用にだけビルドします。`packaging/build.py` は `build/` と `dist/` を作り直し、アーカイブを `dist/` に出します。`v*` タグ push のワークフローは各プラットフォームでテスト、ビルド、隔離環境での凍結 GUI 起動を確認し、成功後にチェックサムを生成して公開します。

UI 翻訳は `tools/i18n/table*.py` で管理します。文字列変更後は翻訳を更新し `python tools/i18n/build.py` を実行します。スクリプトとテストが網羅性・プレースホルダーを確認します。

## ソース構成

| パス | 役割 |
| --- | --- |
| `app.py` | GUI/CLI 入口 |
| `sigwm/background.py` | NumPy/Pillow による紙背景除去 |
| `sigwm/core.py`、`sigwm/vendor/bwm/` | 背景生成、埋込、抽出、耐性確認 |
| `sigwm/imgops.py`、`sigwm/trace.py` | 画像処理、文書解析、検出、照合 |
| `sigwm/service.py`、`sigwm/storage.py` | 一括処理、設定、SQLite、ファイル追跡 |
| `sigwm/backup.py`、`sigwm/secret.py` | バックアップ/復元とパスワード |
| `sigwm/gui/`、`sigwm/i18n.py`、`sigwm/locales/` | UI と多言語化 |
| `packaging/`、`.github/workflows/build.yml` | ポータブルビルドと公開 |
| `tests/` | コア、追跡、データ、画像、翻訳のテスト |
| `tools/signature-remove-bg/` | 独自依存関係を持つ別の背景除去ウェブツール |

旧 Python、batch、PowerShell、OpenStego ファイルも保持されています。古い署名記録は設定から取り込みます。旧記録にはページ上の自動位置検出に必要な境界ボックスがありません。

## 第三者への帰属

透かしコアは MIT の [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) を適応しています。`sigwm/vendor/bwm/LICENSE` を参照してください。同梱 Inter、IBM Plex Mono、Noto フォントは SIL OFL で、通知はフォントとアーカイブに添付します。macOS はシステム UI フォントを使います。別の背景除去ツールには固有のライセンスと依存資料があります。

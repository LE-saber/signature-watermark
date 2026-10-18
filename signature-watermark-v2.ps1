param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
$InputFile = Join-Path $Root "signature.png"
$OpenStego = "D:\signature-watermark\OpenStego\OpenStego\openstego.bat"

$OutDir = Join-Path $Root "out"
$WatermarkDir = Join-Path $OutDir "watermark"
$ImagesDir = Join-Path $OutDir "images"

function Read-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "找不到 .env：$Path"
    }

    $vars = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $s = $line.Trim()
        if (-not $s -or $s.StartsWith("#")) { continue }

        $idx = $s.IndexOf("=")
        if ($idx -lt 1) { continue }

        $name = $s.Substring(0, $idx).Trim()
        $value = $s.Substring($idx + 1).Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $vars[$name] = $value
    }

    return $vars
}

if (-not (Test-Path -LiteralPath $InputFile)) {
    throw "找不到签名母版：$InputFile"
}

if (-not (Test-Path -LiteralPath $OpenStego)) {
    throw "找不到 OpenStego：$OpenStego"
}

New-Item -ItemType Directory -Path $WatermarkDir -Force | Out-Null
New-Item -ItemType Directory -Path $ImagesDir -Force | Out-Null

$envVars = Read-DotEnv -Path $EnvFile

if (-not $envVars.ContainsKey("OPENSTEGO_PASSWORD") -or
    [string]::IsNullOrWhiteSpace($envVars["OPENSTEGO_PASSWORD"])) {
    throw ".env 中缺少 OPENSTEGO_PASSWORD"
}

$Password = $envVars["OPENSTEGO_PASSWORD"]

$Purpose = Read-Host "PURPOSE [signature-use]"
if ([string]::IsNullOrWhiteSpace($Purpose)) {
    $Purpose = "signature-use"
}
$Purpose = $Purpose.Trim()

$Id = "SIG-{0}-{1}" -f `
    (Get-Date -Format "yyyyMMdd"), `
    ([guid]::NewGuid().ToString("N").Substring(0,8).ToUpper())

$Created = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")

$MetaFile = Join-Path $WatermarkDir "$Id.txt"
$OutputFile = Join-Path $ImagesDir "$Id.png"
$LatestFile = Join-Path $ImagesDir "signature_watermarked.png"

@"
ID=$Id
CREATED=$Created
PURPOSE=$Purpose
"@ | Set-Content -LiteralPath $MetaFile -Encoding UTF8

Write-Host ""
Write-Host "正在生成..."
Write-Host "ID      : $Id"
Write-Host "PURPOSE : $Purpose"

& $OpenStego embed `
    -a randomlsb `
    -mf $MetaFile `
    -cf $InputFile `
    -sf $OutputFile `
    -e `
    -A AES256 `
    -p $Password

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $OutputFile)) {
    throw "OpenStego 嵌入失败。"
}

Copy-Item -LiteralPath $OutputFile -Destination $LatestFile -Force

# 自动验证
$VerifyDir = Join-Path $OutDir ".verify-$Id"
New-Item -ItemType Directory -Path $VerifyDir -Force | Out-Null

try {
    & $OpenStego extract `
        -a randomlsb `
        -sf $OutputFile `
        -xd $VerifyDir `
        -p $Password

    if ($LASTEXITCODE -ne 0) {
        throw "OpenStego 验证提取失败。"
    }

    $Extracted = Join-Path $VerifyDir ([IO.Path]::GetFileName($MetaFile))

    if (-not (Test-Path -LiteralPath $Extracted)) {
        throw "验证失败：没有找到提取出的备注文件。"
    }

    $OriginalHash = (Get-FileHash -LiteralPath $MetaFile -Algorithm SHA256).Hash
    $ExtractedHash = (Get-FileHash -LiteralPath $Extracted -Algorithm SHA256).Hash

    if ($OriginalHash -ne $ExtractedHash) {
        throw "验证失败：提取出的备注与原备注不一致。"
    }
}
finally {
    Remove-Item -LiteralPath $VerifyDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "完成，并已自动验证水印。"
Write-Host "水印记录：$MetaFile"
Write-Host "归档图片：$OutputFile"
Write-Host "最新图片：$LatestFile"

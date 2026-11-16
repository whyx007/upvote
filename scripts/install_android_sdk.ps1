<#
.SYNOPSIS
    安装 Android 命令行构建工具链（不装 Android Studio，不装 Gradle）。

.DESCRIPTION
    本项目用 aapt2 + javac + d8 + zipalign + apksigner 手工出包，
    因此只需要 cmdline-tools / build-tools / platform 三样东西。

    产物落在 tools\android-sdk（已 gitignore）。
    环境变量只在本进程内设置，不污染系统。

.PARAMETER Python
    用于下载 SDK 包的 Python 解释器（Windows 自带 TLS 栈会报 SEC_E_NO_CREDENTIALS，故用 Python 下载）。

.EXAMPLE
    pwsh -File scripts\install_android_sdk.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$BuildTools = '34.0.0',
    [string]$Platform = 'android-34'
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$sdkRoot = Join-Path $repoRoot 'tools\android-sdk'
$toolsDir = Join-Path $repoRoot 'tools'
$zipPath = Join-Path $toolsDir 'cmdline-tools.zip'
$sdkManager = Join-Path $sdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

Write-Step '准备目录'
New-Item -ItemType Directory -Force -Path $toolsDir, $sdkRoot | Out-Null

if (-not (Test-Path $sdkManager)) {
    if (-not (Test-Path $zipPath)) {
        Write-Step '下载 cmdline-tools（约 146MB）'
        $fetcher = Join-Path $PSScriptRoot 'fetch_android_sdk.py'
        if (-not (Test-Path $fetcher)) { throw "缺少下载脚本：$fetcher" }
        & $Python $fetcher
        if ($LASTEXITCODE -ne 0) { throw '下载失败' }
    }

    Write-Step '解压 cmdline-tools'
    $tmp = Join-Path $toolsDir 'cmdline-tools-tmp'
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $tmp -Force

    $inner = Join-Path $tmp 'cmdline-tools'
    $target = Join-Path $sdkRoot 'cmdline-tools\latest'
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Move-Item -Path $inner -Destination $target
    Remove-Item $tmp -Recurse -Force
}
else {
    Write-Step 'cmdline-tools 已存在，跳过下载'
}

$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
if (-not $env:JAVA_HOME) { throw '未设置 JAVA_HOME，需要 JDK 17+' }

Write-Step '接受 SDK 许可证'
$answers = (('y' + "`r`n") * 30)
$answers | & $sdkManager "--sdk_root=$sdkRoot" --licenses 2>&1 | Out-Null

Write-Step "安装 platform-tools / build-tools;$BuildTools / platforms;$Platform"
& $sdkManager "--sdk_root=$sdkRoot" 'platform-tools' "build-tools;$BuildTools" "platforms;$Platform" 2>&1 | ForEach-Object { Write-Host $_ }

Write-Step '完成，已安装：'
Get-ChildItem $sdkRoot -Directory | ForEach-Object { Write-Host ("  " + $_.Name) }
Write-Host ""
Write-Host "ANDROID_HOME = $sdkRoot"
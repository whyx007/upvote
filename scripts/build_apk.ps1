<#
.SYNOPSIS
    构建「星灿点赞」安卓 APK（不依赖 Gradle / Android Studio）。

.DESCRIPTION
    管线：前端 vite 构建 → aapt2 编译/链接资源 → javac → d8 → 塞入 classes.dex
          → zipalign → apksigner 签名。

    前置：
      1. JDK 17+（JAVA_HOME）
      2. 已运行 scripts\install_android_sdk.ps1
      3. 前端依赖已安装（frontend\node_modules）

    产物：android\build\upvote-<版本>.apk

.PARAMETER Node
    node 可执行文件路径。

.PARAMETER Pnpm
    pnpm 入口（.mjs 或命令名）。

.PARAMETER SkipFrontend
    跳过前端构建，直接使用现有 frontend\dist。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1
#>
[CmdletBinding()]
param(
    [string]$BuildTools = '34.0.0',
    [string]$Platform = 'android-34',
    [string]$VersionName = '1.0.0',
    [int]$VersionCode = 1,
    [string]$Node = 'node',
    [string]$Pnpm = 'pnpm',
    [string]$Python = 'python',
    [switch]$SkipFrontend,
    [string]$KeyStorePass = 'upvote-android-2026'
)

# 注意：这里不能用 Stop。javac / keytool / d8 等原生工具会往 stderr 写正常进度，
# PowerShell 5.1 在 Stop 模式下会把原生 stderr 当成终止错误。所有外部工具改为
# 显式检查 $LASTEXITCODE，cmdlet 失败由 Assert-* / 显式判断兜底。
$ErrorActionPreference = 'Continue'

$repoRoot = Split-Path -Parent $PSScriptRoot
$androidDir = Join-Path $repoRoot 'android'
$appMain = Join-Path $androidDir 'app\src\main'
$sdkRoot = Join-Path $repoRoot 'tools\android-sdk'
$buildToolsDir = Join-Path $sdkRoot "build-tools\$BuildTools"
$androidJar = Join-Path $sdkRoot "platforms\$Platform\android.jar"
$buildDir = Join-Path $androidDir 'build'
$genDir = Join-Path $buildDir 'gen'
$classesDir = Join-Path $buildDir 'classes'
$dexDir = Join-Path $buildDir 'dex'
$keystoreDir = Join-Path $androidDir 'keystore'
$keystore = Join-Path $keystoreDir 'upvote.jks'
$assetsWww = Join-Path $appMain 'assets\www'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Assert-Tool($path, $hint) {
    if (-not (Test-Path $path)) { throw "缺少 $path（$hint）" }
}

Write-Step '检查工具链'
if (-not $env:JAVA_HOME) { throw '未设置 JAVA_HOME（需要 JDK 17+）' }
Assert-Tool $androidJar '先运行 scripts\install_android_sdk.ps1'
Assert-Tool (Join-Path $buildToolsDir 'aapt2.exe') '先运行 scripts\install_android_sdk.ps1'
Assert-Tool (Join-Path $buildToolsDir 'd8.bat') '先运行 scripts\install_android_sdk.ps1'
Assert-Tool (Join-Path $buildToolsDir 'zipalign.exe') '先运行 scripts\install_android_sdk.ps1'
Assert-Tool (Join-Path $buildToolsDir 'apksigner.bat') '先运行 scripts\install_android_sdk.ps1'

# ---------------------------------------------------------------- 前端构建
if (-not $SkipFrontend) {
    Write-Step '构建前端（禁用 PWA，资源将打进 APK）'
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
        $env:UPVOTE_APK = '1'
        & $Node $Pnpm build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
    }
    finally {
        Pop-Location
        Remove-Item Env:\UPVOTE_APK -ErrorAction SilentlyContinue
    }
}

$distDir = Join-Path $repoRoot 'frontend\dist'
Assert-Tool $distDir '缺少前端产物，请先构建'

Write-Step '拷贝前端产物到 assets\www'
if (Test-Path $assetsWww) { Remove-Item $assetsWww -Recurse -Force }
New-Item -ItemType Directory -Force -Path $assetsWww | Out-Null
Copy-Item -Path (Join-Path $distDir '*') -Destination $assetsWww -Recurse -Force
if (-not (Test-Path (Join-Path $assetsWww 'index.html'))) {
    throw "拷贝前端产物失败：$assetsWww\index.html 不存在"
}
$staticCount = (Get-ChildItem $assetsWww -Recurse -File | Measure-Object).Count
Write-Host "    $staticCount 个静态文件"

# ---------------------------------------------------------------- 图标
$mipmapProbe = Join-Path $appMain 'res\mipmap-xxhdpi\ic_launcher.png'
if (-not (Test-Path $mipmapProbe)) {
    Write-Step '生成安卓图标'
    & $Python (Join-Path $PSScriptRoot 'gen_android_icons.py')
    if ($LASTEXITCODE -ne 0) { throw '图标生成失败' }
}

# ---------------------------------------------------------------- 清理
Write-Step '清理中间产物'
foreach ($d in @($buildDir)) {
    if (Test-Path $d) { Remove-Item $d -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $genDir, $classesDir, $dexDir | Out-Null

$resZip = Join-Path $buildDir 'resources.zip'
$unsigned = Join-Path $buildDir 'app-unsigned.apk'
$aligned = Join-Path $buildDir 'app-aligned.apk'
$finalApk = Join-Path $buildDir ("upvote-{0}.apk" -f $VersionName)

# ---------------------------------------------------------------- aapt2
Write-Step 'aapt2 编译资源'
& (Join-Path $buildToolsDir 'aapt2.exe') compile --dir (Join-Path $appMain 'res') -o $resZip
if ($LASTEXITCODE -ne 0) { throw 'aapt2 compile 失败' }

Write-Step 'aapt2 链接资源并生成 R.java'
& (Join-Path $buildToolsDir 'aapt2.exe') link `
    -o $unsigned `
    -I $androidJar `
    --manifest (Join-Path $appMain 'AndroidManifest.xml') `
    -A (Join-Path $appMain 'assets') `
    --java $genDir `
    --min-sdk-version 24 `
    --target-sdk-version 34 `
    --version-code $VersionCode `
    --version-name $VersionName `
    --auto-add-overlay `
    $resZip
if ($LASTEXITCODE -ne 0) { throw 'aapt2 link 失败' }

# aapt2（Windows 版）会把 assets/www/index.html 写成 assets\www\index.html（反斜杠），
# 导致设备上 AssetManager.open("www/index.html") 抛 FileNotFoundException。必须规范化。
Write-Step '规范化 APK 内 asset 条目名（反斜杠 -> 正斜杠）'
& $Python (Join-Path $PSScriptRoot 'fix_apk_assets.py') $unsigned
if ($LASTEXITCODE -ne 0) { throw 'asset 条目名规范化失败' }

# ---------------------------------------------------------------- javac
Write-Step 'javac 编译 Java 源码'
$sources = @(Get-ChildItem -Path (Join-Path $appMain 'java') -Recurse -Filter '*.java' | ForEach-Object { $_.FullName })
$sources += @(Get-ChildItem -Path $genDir -Recurse -Filter '*.java' | ForEach-Object { $_.FullName })
if ($sources.Count -eq 0) { throw '没有找到 Java 源码' }

& javac -encoding UTF-8 -source 8 -target 8 -Xlint:-options -nowarn `
    -classpath $androidJar `
    -d $classesDir `
    $sources
if ($LASTEXITCODE -ne 0) { throw 'javac 编译失败' }

# ---------------------------------------------------------------- d8
Write-Step 'd8 生成 classes.dex'
$classesJar = Join-Path $buildDir 'classes.jar'
Push-Location $classesDir
try {
    & jar cf $classesJar .
    if ($LASTEXITCODE -ne 0) { throw 'jar 打包失败' }
}
finally { Pop-Location }

& (Join-Path $buildToolsDir 'd8.bat') `
    --min-api 24 `
    --lib $androidJar `
    --output $dexDir `
    $classesJar
if ($LASTEXITCODE -ne 0) { throw 'd8 失败' }

$dexFile = Join-Path $dexDir 'classes.dex'
Assert-Tool $dexFile 'd8 未产出 classes.dex'

# ---------------------------------------------------------------- 组装 APK
Write-Step '把 classes.dex 塞进 APK'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($unsigned, 'Update')
try {
    $entry = $zip.GetEntry('classes.dex')
    if ($entry) { $entry.Delete() }
    [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zip, $dexFile, 'classes.dex', [System.IO.Compression.CompressionLevel]::Optimal)
}
finally { $zip.Dispose() }

# ---------------------------------------------------------------- 签名
Write-Step '签名'
if (-not (Test-Path $keystore)) {
    New-Item -ItemType Directory -Force -Path $keystoreDir | Out-Null
    Write-Host '    生成自签名 keystore（首次构建）'
    & keytool -genkeypair -v `
        -keystore $keystore `
        -alias upvote `
        -keyalg RSA -keysize 2048 -validity 10000 `
        -storepass $KeyStorePass -keypass $KeyStorePass `
        -dname 'CN=Upvote, OU=Whyx, O=Whyx, L=Wuhan, ST=Hubei, C=CN' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'keytool 生成密钥失败' }
    @(
        '星灿点赞 APK 签名密钥',
        "创建时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "别名: upvote",
        "storepass: $KeyStorePass",
        "keypass: $KeyStorePass",
        '',
        '注意：升级安装必须使用同一把密钥，请务必备份本文件与 upvote.jks'
    ) | Set-Content -Path (Join-Path $keystoreDir 'KEYSTORE.txt') -Encoding UTF8
}

& (Join-Path $buildToolsDir 'zipalign.exe') -p -f 4 $unsigned $aligned
if ($LASTEXITCODE -ne 0) { throw 'zipalign 失败' }

& (Join-Path $buildToolsDir 'apksigner.bat') sign `
    --ks $keystore `
    --ks-key-alias upvote `
    --ks-pass "pass:$KeyStorePass" `
    --key-pass "pass:$KeyStorePass" `
    --out $finalApk `
    $aligned
if ($LASTEXITCODE -ne 0) { throw 'apksigner 签名失败' }

Write-Step '校验签名'
& (Join-Path $buildToolsDir 'apksigner.bat') verify --verbose $finalApk | ForEach-Object { Write-Host "    $_" }
if ($LASTEXITCODE -ne 0) { throw 'APK 签名校验失败' }

$sizeMb = [math]::Round((Get-Item $finalApk).Length / 1MB, 2)
Write-Host ''
Write-Host ('构建完成：' + $finalApk) -ForegroundColor Green
Write-Host ("版本 $VersionName ($VersionCode)，大小 $sizeMb MB") -ForegroundColor Green
# 安卓 APK 构建与发布（星灿点赞）

## 设计思路

APK 不重写业务逻辑，而是把现有 Vue 前端装进安卓壳；后端仍然只有 VPS 上那一个 FastAPI 服务。

```
┌──────────────── APK ────────────────┐
│  MainActivity (WebView)             │
│     ↓ 同源  http://127.0.0.1:<随机端口> │
│  LocalServer（回环 HTTP 服务）        │
│     ├── /assets/** ──→ APK 内置静态资源 │
│     └── /api/**    ──→ 反向代理 ───┐  │
└────────────────────────────────────┼──┘
                                     ↓
                    http://43.133.86.206:9100
                    FastAPI + SQLite（唯一后端）
```

**为什么不用 `WebViewAssetLoader`**：`shouldInterceptRequest()` 拿不到 POST 请求体，
登录（`POST /api/auth/login`）、点赞、Excel 导入都会失效。
换成回环 HTTP 服务后，WebView 面对的是完整的同源 HTTP 环境，
后端**零改动**（不需要加 CORS），前端也**零改动**（`baseURL` 仍是相对路径 `/api`）。

## 代码组成

| 文件 | 作用 |
|---|---|
| `android/app/src/main/java/site/whyx/upvote/MainActivity.java` | WebView 宿主、错误页、返回键、外链跳转 |
| `android/app/src/main/java/site/whyx/upvote/LocalServer.java` | 回环 HTTP：静态资源服务 + `/api` 反向代理 |
| `android/app/src/main/java/site/whyx/upvote/SaveBridge.java` | JS 桥：把 Blob（Excel 导出）存进系统「下载」目录 |
| `android/app/src/main/java/site/whyx/upvote/Config.java` | 后端地址、资源目录（构建期常量） |
| `android/app/src/main/assets/inject.js` | 注入脚本，暴露 `window.UpvoteNative` |
| `android/app/src/main/res/xml/network_security_config.xml` | 明文 HTTP 白名单 |
| `scripts/install_android_sdk.ps1` | 安装 cmdline-tools + build-tools + platform |
| `scripts/fetch_android_sdk.py` | 下载 cmdline-tools（Windows schannel 不可用，改用 Python TLS） |
| `scripts/build_apk.ps1` | 一键出包（aapt2 → javac → d8 → zipalign → apksigner） |
| `scripts/gen_android_icons.py` | 由 Web 图标生成各密度 mipmap |

## 首次准备

前置：JDK 17+ 并设置 `JAVA_HOME`；Node 20+ 与 pnpm。

```powershell
# 1. 安装 Android 命令行工具（约 300MB，落在 tools\android-sdk，已 gitignore）
powershell -ExecutionPolicy Bypass -File scripts\install_android_sdk.ps1

# 2. 安装前端依赖
cd frontend
pnpm install
```

## 构建

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1 -VersionName 1.0.0 -VersionCode 1
```

产物：`android\build\upvote-1.0.0.apk`

脚本内部依次完成：

1. `UPVOTE_APK=1 pnpm build` —— 构建前端并**禁用 PWA**（前端资源已随包，Service Worker 会缓存旧壳）
2. 拷贝 `frontend/dist` → `android/app/src/main/assets/www`
3. `aapt2 compile` + `aapt2 link`（生成 `R.java` 与未签名 APK）
4. `javac`（`-source 8 -target 8`，classpath 指向 `android.jar`）
5. `d8` 生成 `classes.dex`
6. 把 `classes.dex` 塞进 APK、`zipalign -p 4`、`apksigner` 签名
7. `apksigner verify` 自检

> 本机注意事项
> - `.ps1` 必须以 **UTF-8 BOM** 保存，否则 Windows PowerShell 5.1 按 GBK 解析，中文注释会导致语法错误
> - Vite 构建依赖 esbuild 起子进程，受限沙箱（管道受限）会报 `spawn EPERM`
> - 签名密钥：`android/keystore/upvote.jks`，密码记录在同目录 `KEYSTORE.txt`（均已 gitignore）
>   **升级安装必须用同一把密钥**，请务必备份
> - **2026-11-19**：原签名密钥随工作区误删丢失，已重建新密钥（别名 `upvote`，JKS）。
>   此前安装的旧 APK 不能覆盖升级，必须先卸载再安装新签名的 APK。

## 安装到平板/手机

```powershell
# 方式一：把 APK 传到设备，允许「未知来源」后点击安装
# 方式二：adb
adb install -r android\build\upvote-1.0.0.apk
```

也可以直接从 VPS 下载（已发布）：<http://43.133.86.206/upvote.apk>
（由宿主机 Caddy 的 `:80` 站点托管 `/usr/share/caddy/upvote.apk`，适合批量装到教师 Pad。）

## 本地验证（无需真机）

`LocalServer` 的资源来源已抽成 `AssetSource` 接口，因此可以脱离 Android 在桌面 JVM 上跑真实 HTTP 请求，
验证静态资源、SPA 回退、404、路径穿越防护，以及 `/api` 代理（会真实打到 VPS 后端）。

```powershell
$out = 'scripts\android_smoke\out'
New-Item -ItemType Directory -Force -Path $out | Out-Null
javac -encoding UTF-8 -source 8 -target 8 -nowarn -d $out `
  scripts\android_smoke\java\android\util\Log.java `
  scripts\android_smoke\java\LocalServerSmokeTest.java `
  android\app\src\main\java\site\whyx\upvote\LocalServer.java `
  android\app\src\main\java\site\whyx\upvote\Config.java
java "-Dfile.encoding=UTF-8" -cp $out LocalServerSmokeTest frontend\dist
```

预期 `通过 15 项，失败 0 项`。`java\android\util\Log.java` 只是一个打印到 stderr 的桩。

## 构建踩坑（都已在脚本/代码里规避）

| 现象 | 原因 | 处置 |
|---|---|---|
| `spawn EPERM` | esbuild 需要管道拉起子进程，受限沙箱禁止命名管道 | 在 `danger-full-access` 下构建 |
| `.ps1` 报字符串未终止 | Windows PowerShell 5.1 按 GBK 解析无 BOM 的 UTF-8 脚本 | 脚本必须存为 **UTF-8 with BOM** |
| d8 `NullPointerException: String.length() ...` | 本机 d8 8.2.2 处理 javac 21 编出的**匿名内部类**会崩 | 用命名内部类或 lambda（见 `AppWebViewClient`） |
| 登录失败时前端拿不到错误文案 | `setFixedLengthStreamingMode` + 401 → Java 抛 `HttpRetryException` 丢弃响应体 | 代理改为缓冲写入，不用流式模式 |
| keytool/javac 输出被当成致命错误 | `$ErrorActionPreference='Stop'` 会把原生 stderr 当终止错误 | 脚本改为 `Continue` + 显式检查 `$LASTEXITCODE` |
| **设备上打开 App 显示 `Not Found`** | **aapt2（Windows 版）把 asset 名写成 `assets/www\index.html`（反斜杠）**，Android AssetManager 只认 `/`，于是 `open("www/index.html")` 抛 FileNotFoundException、`list("www")` 返回空 | `scripts/fix_apk_assets.py` 在 `aapt2 link` 之后规范化条目名；这一步漏了必现 Not Found |

> 排查提示：`zipfile` 在 Windows 上会自动把条目名里的 `\` 换成 `/`（`os.sep` 替换），
> 所以用 Python 看 APK 条目名会**看不出**这个问题。要判定必须扫原始字节，或用
> `adb logcat` 看 `UpvoteApp` 打印的 `assets root=[...]`。

## 真机调试（无需模拟器）

```powershell
$adb = 'tools\android-sdk\platform-tools\adb.exe'
& $adb devices -l
& $adb install -r -d android\build\upvote-*.apk
& $adb logcat -c; & $adb shell am start -n site.whyx.upvote/.MainActivity
& $adb logcat -d -v time | Select-String 'UpvoteLocalServer|UpvoteApp|UpvoteAssetSource|FATAL'
```

- 日志 tag：`UpvoteLocalServer`（每条请求与代理状态）、`UpvoteApp`（assets 探针）、`UpvoteAssetSource`（兜底路径）
- 截图：`adb shell screencap -p /sdcard/s.png` 再 `adb pull`（PowerShell 的 `>` 重定向会破坏二进制）
- `adb` daemon 若报 `cannot open ...\Temp\adb.log: Permission denied`，把 `TEMP` 指到工作区内再启动
- 小米机型装包报 `INSTALL_FAILED_USER_RESTRICTED`：开发者选项里打开「USB 安装」并点手机上的允许

## 更新策略

| 改动类型 | 需要做什么 |
|---|---|
| 后端业务/数据 | 照旧 `python scripts/deploy_vps.py`，APK 不用动 |
| 前端页面 | 重新构建 APK 并分发（静态资源已打包） |
| 后端地址变更 | 改 `Config.java` 的 `API_ORIGIN`，重新打包 |

## 已知限制

1. **明文 HTTP**：`network_security_config.xml` 只对 `43.133.86.206` 与回环地址放行 cleartext。
   将来域名化（如 `upvote.whyx.site` + Caddy 自动证书）后，应把 `API_ORIGIN` 改成 `https://` 并收紧白名单。
2. **前端随包固化**：网页端更新不会自动同步到已安装的 APK，需要重新发版。
3. **首次启动需联网**：壳能离线打开，但登录必须连到 VPS。
4. **仅服务教师/管理员**：学生不建账号（未成年人数据最小化），APK 不做学生端。
5. **Excel 导出走 JS 桥**：保存到系统「下载」目录；Android 9 及以下落在应用私有目录（系统限制，会在 Toast 里显示路径）。
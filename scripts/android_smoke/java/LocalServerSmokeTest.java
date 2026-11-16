import site.whyx.upvote.LocalServer;

import java.io.ByteArrayOutputStream;
import java.io.FileNotFoundException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 在桌面 JVM 上跑 LocalServer 的冒烟测试：
 * 静态资源、SPA 回退、404、以及 /api 反向代理（真实打到 VPS 后端）。
 *
 * <p>用法：{@code java -cp <classes> LocalServerSmokeTest <dist目录>}
 */
public final class LocalServerSmokeTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) throws Exception {
        Path dist = Paths.get(args.length > 0 ? args[0] : "frontend/dist")
                .toAbsolutePath().normalize();
        if (!Files.isRegularFile(dist.resolve("index.html"))) {
            System.err.println("找不到前端产物：" + dist);
            System.exit(2);
        }

        LocalServer server = new LocalServer(path -> {
            String rel = path.startsWith("www/") ? path.substring("www/".length()) : path;
            Path file = dist.resolve(rel).normalize();
            if (!file.startsWith(dist) || !Files.isRegularFile(file)) {
                throw new FileNotFoundException(path);
            }
            return Files.newInputStream(file);
        });

        int port = server.start();
        String base = "http://127.0.0.1:" + port;
        System.out.println("LocalServer 监听 " + base + "，静态根 " + dist);
        System.out.println();

        try {
            // ---- 静态资源
            Resp index = request(base + "/index.html", "GET", null, null);
            check("GET /index.html 状态 200", index.status == 200, index.status);
            check("GET /index.html 是 HTML", index.contentType != null && index.contentType.contains("text/html"), index.contentType);
            check("GET /index.html 含 app 挂载点", index.body.contains("id=\"app\""), preview(index.body));
            check("未缓存首页(no-cache)", "no-cache".equals(index.cacheControl), index.cacheControl);

            Resp root = request(base + "/", "GET", null, null);
            check("GET / 回退到 index.html", root.status == 200 && root.body.contains("id=\"app\""), root.status);

            // ---- 资源文件
            String assetPath = firstAsset(dist);
            Resp asset = request(base + assetPath, "GET", null, null);
            check("GET " + assetPath + " 状态 200", asset.status == 200, asset.status);
            check("静态资源长缓存", asset.cacheControl != null && asset.cacheControl.contains("immutable"), asset.cacheControl);
            check("静态资源非空", asset.bytes.length > 0, asset.bytes.length + " bytes");

            // ---- 404 / 越权路径
            Resp missing = request(base + "/not-exists.png", "GET", null, null);
            check("GET /not-exists.png 返回 404", missing.status == 404, missing.status);

            Resp traversal = request(base + "/../build.gradle", "GET", null, null);
            check("路径穿越被拒（403/404）", traversal.status == 403 || traversal.status == 404, traversal.status);

            // ---- 反向代理：健康检查
            Resp health = request(base + "/api/health", "GET", null, null);
            check("代理 GET /api/health 200", health.status == 200, health.status);
            check("代理返回 {\"status\":\"ok\"}", health.body.replace(" ", "").contains("\"status\":\"ok\""), preview(health.body));

            // ---- 反向代理：未授权
            Resp me = request(base + "/api/auth/me", "GET", null, null);
            check("代理 GET /api/auth/me 无 token 得 401", me.status == 401, me.status);

            // ---- 反向代理：POST 请求体（登录是 POST，最关键）
            String payload = "{\"username\":\"__smoke_not_exist__\",\"password\":\"wrong-password\"}";
            Resp login = request(base + "/api/auth/login", "POST", payload, "application/json");
            check("代理 POST /api/auth/login 得 401", login.status == 401, login.status);
            check("登录失败文案透传（工号或密码错误）", login.body.contains("工号或密码错误"), preview(login.body));
        } finally {
            server.stop();
        }

        System.out.println();
        System.out.println("通过 " + passed + " 项，失败 " + failed + " 项");
        System.exit(failed == 0 ? 0 : 1);
    }

    // ---------------------------------------------------------------- 辅助

    private static String firstAsset(Path dist) throws Exception {
        Path assets = dist.resolve("assets");
        try (java.util.stream.Stream<Path> s = Files.list(assets)) {
            Path p = s.filter(Files::isRegularFile).findFirst().orElse(null);
            if (p == null) {
                throw new IllegalStateException("dist/assets 为空");
            }
            return "/assets/" + p.getFileName();
        }
    }

    private static void check(String name, boolean ok, Object actual) {
        if (ok) {
            passed++;
            System.out.println("  PASS  " + name);
        } else {
            failed++;
            System.out.println("  FAIL  " + name + "   (实际: " + actual + ")");
        }
    }

    private static String preview(String s) {
        if (s == null) {
            return "null";
        }
        return s.length() <= 120 ? s : s.substring(0, 120) + "...";
    }

    private static final class Resp {
        int status;
        String contentType;
        String cacheControl;
        String body;
        byte[] bytes;
    }

    private static Resp request(String url, String method, String body, String contentType) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(20_000);
        conn.setInstanceFollowRedirects(false);
        if (contentType != null) {
            conn.setRequestProperty("Content-Type", contentType);
        }
        if (body != null) {
            byte[] data = body.getBytes(StandardCharsets.UTF_8);
            conn.setDoOutput(true);
            // 注意：不能用 setFixedLengthStreamingMode，流式模式下收到 401
            // 会抛 HttpRetryException 并丢掉错误响应体
            try (OutputStream os = conn.getOutputStream()) {
                os.write(data);
            }
        }

        Resp resp = new Resp();
        resp.status = conn.getResponseCode();
        resp.contentType = conn.getHeaderField("Content-Type");
        resp.cacheControl = conn.getHeaderField("Cache-Control");
        InputStream is = resp.status >= 400 ? conn.getErrorStream() : conn.getInputStream();
        resp.bytes = is == null ? new byte[0] : readAll(is);
        resp.body = new String(resp.bytes, StandardCharsets.UTF_8);
        conn.disconnect();
        return resp;
    }

    private static byte[] readAll(InputStream is) throws Exception {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] tmp = new byte[8192];
        int n;
        while ((n = is.read(tmp)) != -1) {
            buf.write(tmp, 0, n);
        }
        return buf.toByteArray();
    }

    private LocalServerSmokeTest() {}
}
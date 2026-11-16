package site.whyx.upvote;

import android.util.Log;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 本地回环 HTTP 服务，作为 WebView 的"同源"后端：
 *
 * <ul>
 *   <li>{@code /api/**} → 转发到 {@link Config#API_ORIGIN}（真实 VPS 后端）</li>
 *   <li>其余路径 → 从 APK 的 {@code assets/www} 读取静态文件（SPA 回退 index.html）</li>
 * </ul>
 *
 * <p>之所以不用 {@code WebViewAssetLoader} + {@code shouldInterceptRequest}：
 * 那条路拿不到 POST 请求体，登录、点赞、导入都会失效。
 * 换成回环 HTTP 服务后，WebView 看到的是完整的同源 HTTP 环境，
 * 后端也不需要改 CORS。
 */
public final class LocalServer {

    private static final String TAG = "UpvoteLocalServer";
    private static final int MAX_BODY_BYTES = 32 * 1024 * 1024;

    /** 转发时丢弃的请求头（连接级 + 由 HttpURLConnection 自己管理） */
    private static final Set<String> SKIP_REQUEST_HEADERS = new HashSet<>(Arrays.asList(
            "host", "connection", "keep-alive", "proxy-connection", "transfer-encoding",
            "content-length", "accept-encoding", "te", "trailer", "upgrade",
            "origin", "referer", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"
    ));

    private final AssetSource assets;
    private final ExecutorService pool = Executors.newFixedThreadPool(6);
    private final AtomicBoolean running = new AtomicBoolean(false);
    private ServerSocket serverSocket;
    private Thread acceptThread;
    private String lastAssetError;
    private String lastMissPath = "";

    /** 静态资源来源。安卓侧是 {@link AssetManagerSource}，桌面侧用文件系统，便于本地冒烟测试。 */
    public interface AssetSource {
        InputStream open(String path) throws IOException;

        String[] list(String path) throws IOException;
    }

    public LocalServer(AssetSource assets) {
        this.assets = assets;
    }

    /** 启动服务并返回实际监听端口（随机空闲端口）。 */
    public int start() throws IOException {
        serverSocket = new ServerSocket();
        serverSocket.setReuseAddress(true);
        serverSocket.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 50);
        running.set(true);
        acceptThread = new Thread(this::acceptLoop, "upvote-http-accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
        return serverSocket.getLocalPort();
    }

    public void stop() {
        running.set(false);
        try {
            if (serverSocket != null) {
                serverSocket.close();
            }
        } catch (IOException ignored) {
            // 关闭失败无需处理
        }
        pool.shutdownNow();
    }

    private void acceptLoop() {
        while (running.get()) {
            try {
                final Socket socket = serverSocket.accept();
                pool.execute(() -> handle(socket));
            } catch (IOException e) {
                if (running.get()) {
                    Log.w(TAG, "accept failed: " + e.getMessage());
                }
            }
        }
    }

    private void handle(Socket socket) {
        try (Socket s = socket) {
            s.setSoTimeout(30_000);
            BufferedInputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = new BufferedOutputStream(s.getOutputStream());

            String requestLine = readLine(in);
            if (requestLine == null || requestLine.isEmpty()) {
                return;
            }
            String[] parts = requestLine.split(" ");
            if (parts.length < 2) {
                writeText(out, 400, "Bad Request");
                return;
            }
            String method = parts[0];
            String target = normalizeTarget(parts[1]);
            Log.d(TAG, method + " " + target);

            Map<String, String> headers = readHeaders(in);
            byte[] body = readBody(in, headers);

            if (target.startsWith("/api/") || target.equals("/api")) {
                proxy(method, target, headers, body, out);
            } else {
                serveAsset(method, target, out);
            }
            out.flush();
        } catch (Exception e) {
            Log.w(TAG, "request failed: " + e);
        }
    }

    // ---------------------------------------------------------------- 请求解析

    /**
     * 部分 WebView 会发绝对形式的请求行（{@code GET http://host/path HTTP/1.1}），
     * 这里统一成 origin-form，避免资源查找拿到一整个 URL 而返回 404。
     */
    private static String normalizeTarget(String rawTarget) {
        if (rawTarget == null || rawTarget.isEmpty()) {
            return "/";
        }
        if (rawTarget.startsWith("http://") || rawTarget.startsWith("https://")) {
            try {
                java.net.URI uri = java.net.URI.create(rawTarget);
                String path = uri.getRawPath();
                String query = uri.getRawQuery();
                if (path == null || path.isEmpty()) {
                    path = "/";
                }
                return query == null ? path : path + "?" + query;
            } catch (Exception ignored) {
                // 解析失败则按原样处理
            }
        }
        return rawTarget;
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream(128);
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') {
                break;
            }
            if (c != '\r') {
                buf.write(c);
            }
            if (buf.size() > 16_384) {
                break;
            }
        }
        if (c == -1 && buf.size() == 0) {
            return null;
        }
        return new String(buf.toByteArray(), StandardCharsets.ISO_8859_1);
    }

    private static Map<String, String> readHeaders(InputStream in) throws IOException {
        Map<String, String> headers = new HashMap<>();
        String line;
        while ((line = readLine(in)) != null && !line.isEmpty()) {
            int idx = line.indexOf(':');
            if (idx > 0) {
                headers.put(line.substring(0, idx).trim().toLowerCase(Locale.ROOT),
                        line.substring(idx + 1).trim());
            }
        }
        return headers;
    }

    private static byte[] readBody(InputStream in, Map<String, String> headers) throws IOException {
        String te = headers.get("transfer-encoding");
        if (te != null && te.toLowerCase(Locale.ROOT).contains("chunked")) {
            return readChunked(in);
        }
        String cl = headers.get("content-length");
        if (cl == null) {
            return null;
        }
        int len;
        try {
            len = Integer.parseInt(cl.trim());
        } catch (NumberFormatException e) {
            return null;
        }
        if (len <= 0 || len > MAX_BODY_BYTES) {
            return null;
        }
        byte[] data = new byte[len];
        int off = 0;
        while (off < len) {
            int n = in.read(data, off, len - off);
            if (n < 0) {
                break;
            }
            off += n;
        }
        return off == len ? data : null;
    }

    private static byte[] readChunked(InputStream in) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        while (true) {
            String sizeLine = readLine(in);
            if (sizeLine == null) {
                break;
            }
            int semi = sizeLine.indexOf(';');
            String hex = (semi >= 0 ? sizeLine.substring(0, semi) : sizeLine).trim();
            int size;
            try {
                size = Integer.parseInt(hex, 16);
            } catch (NumberFormatException e) {
                break;
            }
            if (size == 0) {
                // 读掉 trailer
                String trailer;
                while ((trailer = readLine(in)) != null && !trailer.isEmpty()) {
                    // ignore
                }
                break;
            }
            byte[] chunk = new byte[size];
            int off = 0;
            while (off < size) {
                int n = in.read(chunk, off, size - off);
                if (n < 0) {
                    break;
                }
                off += n;
            }
            body.write(chunk, 0, off);
            if (body.size() > MAX_BODY_BYTES) {
                break;
            }
            readLine(in); // 块尾 CRLF
        }
        return body.toByteArray();
    }

    // ---------------------------------------------------------------- 反向代理

    private void proxy(String method, String target, Map<String, String> headers,
                       byte[] body, OutputStream out) throws IOException {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(Config.API_ORIGIN + target).openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(15_000);
            conn.setReadTimeout(60_000);
            conn.setInstanceFollowRedirects(false);
            conn.setUseCaches(false);
            conn.setDoInput(true);
            conn.setRequestProperty("Accept-Encoding", "identity");

            for (Map.Entry<String, String> e : headers.entrySet()) {
                if (SKIP_REQUEST_HEADERS.contains(e.getKey())) {
                    continue;
                }
                conn.setRequestProperty(e.getKey(), e.getValue());
            }

            if (body != null && body.length > 0) {
                conn.setDoOutput(true);
                // 不能用 setFixedLengthStreamingMode：流式模式下 HttpURLConnection
                // 遇到 401 会抛 HttpRetryException 并丢弃错误响应体，
                // 导致登录失败时前端拿不到「工号或密码错误」。
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(body);
                }
            }

            int code = conn.getResponseCode();
            Log.d(TAG, "proxy " + method + " " + target + " -> " + code);
            InputStream ris = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            byte[] respBody = ris == null ? new byte[0] : readAll(ris, MAX_BODY_BYTES);

            String contentType = conn.getHeaderField("Content-Type");
            if (contentType == null) {
                contentType = "application/json; charset=utf-8";
            }
            String disposition = conn.getHeaderField("Content-Disposition");
            String cacheControl = conn.getHeaderField("Cache-Control");

            StringBuilder head = new StringBuilder(256);
            head.append("HTTP/1.1 ").append(code).append(' ').append(reason(code)).append("\r\n");
            head.append("Content-Type: ").append(contentType).append("\r\n");
            head.append("Content-Length: ").append(respBody.length).append("\r\n");
            head.append("Cache-Control: ").append(cacheControl == null ? "no-store" : cacheControl).append("\r\n");
            if (disposition != null && isAscii(disposition)) {
                head.append("Content-Disposition: ").append(disposition).append("\r\n");
            }
            head.append("Connection: close\r\n\r\n");

            out.write(head.toString().getBytes(StandardCharsets.ISO_8859_1));
            out.write(respBody);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    // ---------------------------------------------------------------- 静态资源

    private void serveAsset(String method, String target, OutputStream out) throws IOException {
        String path = target;
        int q = path.indexOf('?');
        if (q >= 0) {
            path = path.substring(0, q);
        }
        try {
            path = URLDecoder.decode(path, "UTF-8");
        } catch (Exception ignored) {
            // 解码失败按原样处理
        }
        if (path.isEmpty() || path.equals("/")) {
            path = "/index.html";
        }
        if (path.contains("..")) {
            writeText(out, 403, "Forbidden");
            return;
        }

        lastMissPath = path;
        lastAssetError = null;
        byte[] data = readAssetOrNull(Config.ASSET_DIR + path);
        if (data == null && !hasExtension(path)) {
            data = readAssetOrNull(Config.ASSET_DIR + "/index.html");
            if (data != null) {
                path = "/index.html";
            }
        }
        if (data == null) {
            Log.w(TAG, "asset miss: " + Config.ASSET_DIR + path);
            writeText(out, 404, "Not Found: " + path + "\n" + describeAssets());
            return;
        }

        boolean immutable = path.startsWith("/assets/");
        StringBuilder head = new StringBuilder(196);
        head.append("HTTP/1.1 200 OK\r\n");
        head.append("Content-Type: ").append(mimeOf(path)).append("\r\n");
        head.append("Content-Length: ").append(data.length).append("\r\n");
        head.append("Cache-Control: ").append(immutable ? "public, max-age=31536000, immutable" : "no-cache").append("\r\n");
        head.append("Connection: close\r\n\r\n");
        out.write(head.toString().getBytes(StandardCharsets.ISO_8859_1));
        if (!"HEAD".equals(method)) {
            out.write(data);
        }
    }

    private byte[] readAssetOrNull(String assetPath) {
        try (InputStream is = assets.open(assetPath)) {
            return readAll(is, 64 * 1024 * 1024);
        } catch (IOException e) {
            lastAssetError = assetPath + " -> " + e;
            Log.w(TAG, "open asset failed: " + lastAssetError);
            return null;
        }
    }

    /** 404 时把 APK 里实际可见的 assets 和最近一次异常都列出来，方便在设备上定位。 */
    private String describeAssets() {
        StringBuilder sb = new StringBuilder();
        sb.append("requested asset: ").append(Config.ASSET_DIR).append(lastMissPath).append('\n');
        if (lastAssetError != null) {
            sb.append("last error: ").append(lastAssetError).append('\n');
        }
        sb.append("assets root: ").append(joinList("")).append('\n');
        sb.append("assets/").append(Config.ASSET_DIR).append(": ").append(joinList(Config.ASSET_DIR));
        return sb.toString();
    }

    private String joinList(String dir) {
        try {
            String[] items = assets.list(dir);
            if (items == null || items.length == 0) {
                return "(empty)";
            }
            return String.join(", ", items);
        } catch (IOException e) {
            return "(list failed: " + e + ")";
        }
    }

    private static byte[] readAll(InputStream is, int limit) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream(16 * 1024);
        byte[] tmp = new byte[16 * 1024];
        int n;
        while ((n = is.read(tmp)) != -1) {
            buf.write(tmp, 0, n);
            if (buf.size() > limit) {
                break;
            }
        }
        return buf.toByteArray();
    }

    private static boolean hasExtension(String path) {
        int slash = path.lastIndexOf('/');
        int dot = path.lastIndexOf('.');
        return dot > slash;
    }

    private static boolean isAscii(String s) {
        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) > 127) {
                return false;
            }
        }
        return true;
    }

    private static String mimeOf(String path) {
        String p = path.toLowerCase(Locale.ROOT);
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html; charset=utf-8";
        if (p.endsWith(".js") || p.endsWith(".mjs")) return "application/javascript; charset=utf-8";
        if (p.endsWith(".css")) return "text/css; charset=utf-8";
        if (p.endsWith(".json")) return "application/json; charset=utf-8";
        if (p.endsWith(".webmanifest") || p.endsWith(".manifest")) return "application/manifest+json; charset=utf-8";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".gif")) return "image/gif";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".ico")) return "image/x-icon";
        if (p.endsWith(".woff2")) return "font/woff2";
        if (p.endsWith(".woff")) return "font/woff";
        if (p.endsWith(".ttf")) return "font/ttf";
        if (p.endsWith(".txt")) return "text/plain; charset=utf-8";
        if (p.endsWith(".map")) return "application/json; charset=utf-8";
        return "application/octet-stream";
    }

    private static void writeText(OutputStream out, int code, String text) throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        String head = "HTTP/1.1 " + code + " " + reason(code) + "\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.ISO_8859_1));
        out.write(body);
    }

    private static String reason(int code) {
        switch (code) {
            case 200: return "OK";
            case 201: return "Created";
            case 204: return "No Content";
            case 301: return "Moved Permanently";
            case 302: return "Found";
            case 304: return "Not Modified";
            case 400: return "Bad Request";
            case 401: return "Unauthorized";
            case 403: return "Forbidden";
            case 404: return "Not Found";
            case 405: return "Method Not Allowed";
            case 409: return "Conflict";
            case 422: return "Unprocessable Entity";
            case 429: return "Too Many Requests";
            case 500: return "Internal Server Error";
            case 502: return "Bad Gateway";
            case 503: return "Service Unavailable";
            case 504: return "Gateway Timeout";
            default: return "Status";
        }
    }
}
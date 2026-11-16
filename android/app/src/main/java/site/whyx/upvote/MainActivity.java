package site.whyx.upvote;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup.LayoutParams;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * 星灿点赞安卓客户端主界面。
 *
 * <p>前端资源随 APK 打包，由 {@link LocalServer} 在 127.0.0.1 上提供服务，
 * 同源转发 {@code /api/**} 到 VPS 后端，因此 WebView 内是一个完整的同源 HTTP 应用。
 */
public class MainActivity extends Activity {

    private static final String TAG = "UpvoteApp";
    private static final int MATCH = LayoutParams.MATCH_PARENT;
    private static final int WRAP = LayoutParams.WRAP_CONTENT;

    private WebView webView;
    private LocalServer server;
    private View errorView;
    private TextView errorDetail;
    private String baseUrl;
    private String injectScript;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);
        setContentView(root);

        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(MATCH, MATCH));

        errorView = buildErrorView();
        errorView.setVisibility(View.GONE);
        root.addView(errorView, new FrameLayout.LayoutParams(MATCH, MATCH));

        injectScript = readAsset(Config.INJECT_SCRIPT);

        try {
            server = new LocalServer(getAssets()::open);
            int port = server.start();
            baseUrl = "http://127.0.0.1:" + port + "/";
        } catch (IOException e) {
            Log.e(TAG, "local server start failed", e);
            showError("内置资源服务启动失败：" + e.getMessage());
            return;
        }

        configureWebView();
        webView.loadUrl(baseUrl + "index.html");
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // localStorage：登录态存这里
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setJavaScriptCanOpenWindowsAutomatically(false);
        s.setSupportMultipleWindows(false);
        s.setUserAgentString(s.getUserAgentString() + " UpvoteApp/1.0");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
            webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        }

        webView.addJavascriptInterface(new SaveBridge(this), "AndroidBridge");

        webView.setWebViewClient(new AppWebViewClient(this));
    }

    /**
     * 命名为静态内部类，而不是匿名类。
     *
     * <p>本机 d8 8.2.2 处理 javac 21 编出的匿名内部类（如 {@code new WebViewClient(){...}}）
     * 会抛 {@code NullPointerException: String.length() because "<parameter1>" is null}，
     * 命名内部类与 lambda 不受影响。
     */
    private static final class AppWebViewClient extends WebViewClient {

        private final MainActivity activity;

        AppWebViewClient(MainActivity activity) {
            this.activity = activity;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (uri == null) {
                return false;
            }
            String url = uri.toString();
            if (activity.baseUrl != null && url.startsWith(activity.baseUrl)) {
                return false;   // 应用内部页面，WebView 自己处理
            }
            activity.openExternally(uri);
            return true;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (url == null || activity.baseUrl == null || !url.startsWith(activity.baseUrl)) {
                return;
            }
            activity.errorView.setVisibility(View.GONE);
            if (activity.injectScript != null && !activity.injectScript.isEmpty()) {
                view.evaluateJavascript(activity.injectScript, null);
            }
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request != null && request.isForMainFrame()) {
                CharSequence desc = error == null ? null : error.getDescription();
                activity.showError("页面加载失败" + (desc == null ? "" : "：" + desc));
            }
        }
    }

    private void openExternally(Uri uri) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, uri);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (Exception e) {
            Log.w(TAG, "no activity for " + uri, e);
        }
    }

    // ---------------------------------------------------------------- 错误页

    private View buildErrorView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.WHITE);
        int pad = dp(24);
        box.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText(getString(R.string.error_title));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER);
        box.addView(title, new LinearLayout.LayoutParams(WRAP, WRAP));

        errorDetail = new TextView(this);
        errorDetail.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        errorDetail.setGravity(Gravity.CENTER);
        errorDetail.setTextColor(Color.parseColor("#969799"));
        LinearLayout.LayoutParams detailParams = new LinearLayout.LayoutParams(MATCH, WRAP);
        detailParams.topMargin = dp(8);
        box.addView(errorDetail, detailParams);

        Button retry = new Button(this);
        retry.setText(getString(R.string.error_retry));
        retry.setOnClickListener(v -> {
            errorView.setVisibility(View.GONE);
            if (baseUrl != null) {
                webView.loadUrl(baseUrl + "index.html");
            }
        });
        LinearLayout.LayoutParams btnParams = new LinearLayout.LayoutParams(WRAP, WRAP);
        btnParams.topMargin = dp(20);
        box.addView(retry, btnParams);

        return box;
    }

    private void showError(String detail) {
        if (errorDetail != null) {
            errorDetail.setText(detail);
        }
        if (errorView != null) {
            errorView.setVisibility(View.VISIBLE);
            errorView.bringToFront();
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    // ---------------------------------------------------------------- 生命周期

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.removeJavascriptInterface("AndroidBridge");
            webView.loadUrl("about:blank");
            webView.destroy();
            webView = null;
        }
        if (server != null) {
            server.stop();
            server = null;
        }
        super.onDestroy();
    }

    private String readAsset(String name) {
        try (InputStream is = getAssets().open(name)) {
            ByteArrayOutputStream buf = new ByteArrayOutputStream(4096);
            byte[] tmp = new byte[4096];
            int n;
            while ((n = is.read(tmp)) != -1) {
                buf.write(tmp, 0, n);
            }
            return new String(buf.toByteArray(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            Log.w(TAG, "missing asset: " + name);
            return null;
        }
    }
}
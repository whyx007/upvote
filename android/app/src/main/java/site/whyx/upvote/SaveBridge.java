package site.whyx.upvote;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

/**
 * 提供给网页的保存桥。
 *
 * <p>WebView 里 {@code <a download>} 不会触发下载，管理端的 Excel 导出会静默失败，
 * 因此前端 {@code downloadBlob()} 在检测到 {@code window.UpvoteNative} 时改走这里：
 * JS 把 Blob 转成 base64 → {@link #saveBase64} 落盘到系统「下载」目录。
 */
public final class SaveBridge {

    private static final String TAG = "UpvoteSaveBridge";
    private static final String DEFAULT_MIME = "application/octet-stream";

    private final Activity activity;

    SaveBridge(Activity activity) {
        this.activity = activity;
    }

    @JavascriptInterface
    public void saveBase64(String name, String mime, String base64) {
        String safeName = sanitize(name);
        String safeMime = (mime == null || mime.trim().isEmpty()) ? DEFAULT_MIME : mime.trim();
        try {
            byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
            String where = write(safeName, safeMime, bytes);
            toast("已保存：" + where);
        } catch (Exception e) {
            Log.w(TAG, "save failed", e);
            toast("保存失败：" + e.getMessage());
        }
    }

    private String write(String name, String mime, byte[] bytes) throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentResolver resolver = activity.getContentResolver();
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, name);
            values.put(MediaStore.Downloads.MIME_TYPE, mime);
            values.put(MediaStore.Downloads.IS_PENDING, 1);
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                throw new IllegalStateException("无法创建下载项");
            }
            try (OutputStream os = resolver.openOutputStream(uri)) {
                if (os == null) {
                    throw new IllegalStateException("无法写入下载项");
                }
                os.write(bytes);
            }
            values.clear();
            values.put(MediaStore.Downloads.IS_PENDING, 0);
            resolver.update(uri, values, null, null);
            return "下载/" + name;
        }

        File dir = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) {
            dir = activity.getFilesDir();
        }
        File out = new File(dir, name);
        try (FileOutputStream fos = new FileOutputStream(out)) {
            fos.write(bytes);
        }
        return out.getAbsolutePath();
    }

    private static String sanitize(String name) {
        String n = (name == null || name.trim().isEmpty()) ? "export.bin" : name.trim();
        n = n.replaceAll("[\\\\/:*?\"<>|]", "_");
        if (n.length() > 120) {
            n = n.substring(n.length() - 120);
        }
        return n;
    }

    private void toast(final String message) {
        activity.runOnUiThread(() -> Toast.makeText(activity, message, Toast.LENGTH_LONG).show());
    }
}
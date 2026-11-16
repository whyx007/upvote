package site.whyx.upvote;

import android.app.Activity;
import android.content.pm.ApplicationInfo;
import android.util.Log;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Enumeration;
import java.util.Set;
import java.util.TreeSet;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * 静态资源读取：优先 {@link AssetManagerSource}，失败时回退到直接读 APK 内的 zip。
 *
 * <p>回退路径的意义：只要 APK 里确实有 {@code assets/www/**}，即使设备上的
 * AssetManager 因为某些兼容性原因打不开，页面也能正常加载。
 */
final class HybridAssetSource implements LocalServer.AssetSource {

    private static final String TAG = "UpvoteAssetSource";

    private final AssetManagerSource primary;
    private final ZipFile apk;
    private volatile boolean primaryBroken;

    HybridAssetSource(Activity activity) {
        this.primary = new AssetManagerSource(activity.getAssets());
        this.apk = openApk(activity.getApplicationInfo());
        Log.i(TAG, "sourceDir=" + activity.getApplicationInfo().sourceDir + " zipOpened=" + (apk != null));
    }

    private static ZipFile openApk(ApplicationInfo info) {
        try {
            ZipFile zip = new ZipFile(new File(info.sourceDir));
            Log.i(TAG, "apk zip entries=" + zip.size());
            return zip;
        } catch (IOException e) {
            Log.w(TAG, "cannot open apk zip: " + e);
            return null;
        }
    }

    @Override
    public InputStream open(String path) throws IOException {
        if (!primaryBroken) {
            try {
                return primary.open(path);
            } catch (IOException primaryError) {
                // 只有在 zip 里确实存在时才判定 AssetManager 不可用，
                // 否则只是普通的资源不存在（例如 favicon.ico），不应污染状态。
                try {
                    InputStream fromZip = openFromZip(path);
                    primaryBroken = true;
                    Log.w(TAG, "AssetManager failed (" + primaryError + "), using apk zip for " + path);
                    return fromZip;
                } catch (IOException zipError) {
                    Log.w(TAG, "zip fallback failed for " + path + ": " + zipError
                            + " (zipOpened=" + (apk != null) + ")");
                    throw primaryError;
                }
            }
        }
        return openFromZip(path);
    }

    @Override
    public String[] list(String path) throws IOException {
        if (!primaryBroken) {
            try {
                return primary.list(path);
            } catch (IOException e) {
                primaryBroken = true;
            }
        }
        return listFromZip(path);
    }

    private InputStream openFromZip(String path) throws IOException {
        if (apk == null) {
            throw new FileNotFoundException(path + " (apk zip unavailable)");
        }
        ZipEntry entry = apk.getEntry("assets/" + path);
        if (entry == null) {
            throw new FileNotFoundException(path);
        }
        return apk.getInputStream(entry);
    }

    private String[] listFromZip(String path) {
        if (apk == null) {
            return new String[0];
        }
        String prefix = path.isEmpty() ? "assets/" : "assets/" + path + "/";
        Set<String> names = new TreeSet<>();
        Enumeration<? extends ZipEntry> entries = apk.entries();
        while (entries.hasMoreElements()) {
            String name = entries.nextElement().getName();
            if (!name.startsWith(prefix) || name.length() == prefix.length()) {
                continue;
            }
            String rest = name.substring(prefix.length());
            int slash = rest.indexOf('/');
            names.add(slash > 0 ? rest.substring(0, slash) + "/" : rest);
        }
        return names.toArray(new String[0]);
    }
}
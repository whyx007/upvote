package site.whyx.upvote;

import android.content.res.AssetManager;

import java.io.IOException;
import java.io.InputStream;

/**
 * 用 {@link AssetManager} 实现 {@link LocalServer.AssetSource}。
 *
 * <p>单独写成命名类而不是 lambda：本机 d8 对匿名类有兼容问题（见 LocalServer 注释）。
 */
final class AssetManagerSource implements LocalServer.AssetSource {

    private final AssetManager assets;

    AssetManagerSource(AssetManager assets) {
        this.assets = assets;
    }

    @Override
    public InputStream open(String path) throws IOException {
        return assets.open(path);
    }

    @Override
    public String[] list(String path) throws IOException {
        return assets.list(path);
    }
}
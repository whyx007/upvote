package site.whyx.upvote;

/** 构建期常量：改后端地址后重新打包即可。 */
public final class Config {
    /** VPS 后端地址（FastAPI + 静态资源） */
    public static final String API_ORIGIN = "http://43.133.86.206:9100";

    /** APK 内前端资源目录（assets/www） */
    public static final String ASSET_DIR = "www";

    /** 注入脚本（assets/inject.js） */
    public static final String INJECT_SCRIPT = "inject.js";

    private Config() {}
}
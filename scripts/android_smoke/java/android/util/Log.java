package android.util;

/** 桌面冒烟测试用的 Log 桩：让 LocalServer 能脱离 Android 运行时编译运行。 */
public final class Log {
    private Log() {}

    public static int w(String tag, String msg) {
        System.err.println("W/" + tag + ": " + msg);
        return 0;
    }

    public static int w(String tag, String msg, Throwable tr) {
        return w(tag, msg);
    }

    public static int e(String tag, String msg) {
        System.err.println("E/" + tag + ": " + msg);
        return 0;
    }

    public static int e(String tag, String msg, Throwable tr) {
        return e(tag, msg);
    }

    public static int i(String tag, String msg) { return 0; }

    public static int d(String tag, String msg) { return 0; }
}
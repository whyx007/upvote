"""修复 aapt2 在 Windows 上产出的反斜杠 asset 条目名。

aapt2（Windows 版）会把 ``assets/www/index.html`` 写成 ``assets/www\\index.html``，
导致 Android 的 AssetManager 无法按目录访问：
``open("www/index.html")`` 抛 FileNotFoundException、``list("www")`` 返回空。

坑：Python 的 ``zipfile`` 在 Windows 上会把读到的 ``\\`` 自动换成 ``/``（``os.sep`` 替换），
所以必须用 ``ZipInfo.orig_filename`` 才能看到真实条目名；写出时同理。
本脚本用 orig_filename 判定并重写条目名，其余（压缩方式、时间戳、属性）保持不变。

用法：python scripts/fix_apk_assets.py <apk>
退出码：0 成功；1 失败；2 修复后仍存在反斜杠。
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile


def _raw_has_backslash(apk_path: str) -> bool:
    """直接扫原始字节，绕开 zipfile 的路径规范化。"""
    needle = b"assets/"
    with open(apk_path, "rb") as fh:
        data = fh.read()
    idx = data.find(needle)
    while idx != -1:
        end = idx
        while end < len(data) and data[end] not in b"\x00\r\n":
            end += 1
        chunk = data[idx:end]
        # 只关心看起来像条目名的片段（可打印 ASCII 且含反斜杠）
        if b"\\" in chunk and all(32 <= b < 127 for b in chunk):
            return True
        idx = data.find(needle, idx + 1)
    return False


def fix(apk_path: str) -> int:
    if not os.path.isfile(apk_path):
        print("找不到 APK：%s" % apk_path, file=sys.stderr)
        return 1

    with zipfile.ZipFile(apk_path) as zf:
        infos = zf.infolist()
        need = [info for info in infos if "\\" in info.orig_filename]
        if not need:
            print("条目名已规范，无需修改")
            return 0
        payloads = {info.orig_filename: zf.read(info) for info in infos}
        metas = {info.orig_filename: info for info in infos}

    tmp_path = apk_path + ".tmp"
    try:
        with zipfile.ZipFile(tmp_path, "w") as out:
            for orig, info in metas.items():
                name = orig.replace("\\", "/")
                new_info = zipfile.ZipInfo(name, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                new_info.internal_attr = info.internal_attr
                new_info.create_system = info.create_system
                out.writestr(new_info, payloads[orig])
        shutil.move(tmp_path, apk_path)
        print("已规范化 %d 个条目名" % len(need))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if _raw_has_backslash(apk_path):
        print("修复后仍存在反斜杠条目", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python scripts/fix_apk_assets.py <apk>", file=sys.stderr)
        sys.exit(1)
    sys.exit(fix(sys.argv[1]))
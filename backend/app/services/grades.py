"""年级口径：统一为七年级/八年级/九年级，兼容旧的初一/初二/初三与 7/8/9 年级写法。"""
import re

GRADES = ("七年级", "八年级", "九年级")
CN_DIGITS = "零一二三四五六七八九"
CN_VALUES = {char: index for index, char in enumerate(CN_DIGITS)}


def int_to_chinese(number: int) -> str:
    """1..99 转中文数字；班级编号够用，超出时回退阿拉伯数字。"""
    if number <= 0 or number >= 100:
        return str(number)
    if number < 10:
        return CN_DIGITS[number]
    tens, ones = divmod(number, 10)
    prefix = "十" if tens == 1 else CN_DIGITS[tens] + "十"
    return prefix + (CN_DIGITS[ones] if ones else "")


def chinese_to_int(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = CN_VALUES.get(left, 1) if left else 1
        ones = CN_VALUES.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(raw) == 1 and raw in CN_VALUES:
        return CN_VALUES[raw]
    return None

# 键越长越优先匹配；值统一为规范年级名
GRADE_ALIASES = {
    "七年级": "七年级",
    "初一": "七年级",
    "7年级": "七年级",
    "初中一年级": "七年级",
    "八年级": "八年级",
    "初二": "八年级",
    "8年级": "八年级",
    "初中二年级": "八年级",
    "九年级": "九年级",
    "初三": "九年级",
    "9年级": "九年级",
    "初中三年级": "九年级",
}

_ALIASES_LONGEST_FIRST = sorted(GRADE_ALIASES, key=len, reverse=True)


def normalize_grade(value: str | None) -> str | None:
    raw = (value or "").strip().replace(" ", "")
    if not raw:
        return None
    if raw in GRADE_ALIASES:
        return GRADE_ALIASES[raw]
    for alias in _ALIASES_LONGEST_FIRST:
        if raw.startswith(alias):
            return GRADE_ALIASES[alias]
    return raw


def grade_of_class(class_name: str | None) -> str | None:
    raw = (class_name or "").strip().replace(" ", "")
    for alias in _ALIASES_LONGEST_FIRST:
        if raw.startswith(alias):
            return GRADE_ALIASES[alias]
    return None


def class_no_of(class_name: str | None) -> int | None:
    raw = (class_name or "").strip()
    match = re.search(r"([0-9]+|[一二三四五六七八九十]+)\s*班?\s*$", raw)
    if not match:
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else chinese_to_int(token)


def grade_rank(grade: str | None) -> int:
    normalized = normalize_grade(grade)
    try:
        return GRADES.index(normalized)
    except ValueError:
        return len(GRADES)


def class_sort_key(class_name: str):
    return (grade_rank(grade_of_class(class_name)), class_no_of(class_name) or 0, class_name or "")


def build_class_name(grade: str | None, class_no: int) -> str:
    return f"{normalize_grade(grade) or ''}{int_to_chinese(class_no)}班"


def is_known_grade(value: str | None) -> bool:
    return normalize_grade(value) in GRADES


def grade_values(value: str | None) -> list[str]:
    """返回某年级在历史数据中可能出现的所有写法。"""
    target = normalize_grade(value)
    if not target:
        return []
    return [alias for alias, canonical in GRADE_ALIASES.items() if canonical == target]
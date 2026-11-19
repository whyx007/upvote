"""小组名称自动续号：已有“第一组”时，批量新增从“第二组”开始。"""
import re

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_GROUP_RE = re.compile(r"^(第)?([0-9]+|[零〇一二两三四五六七八九十百]+)组$")


def _cn_to_int(text: str) -> int | None:
    total = 0
    current = 0
    for char in text:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def _int_to_cn(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    if value < 1000:
        head = digits[value // 100] + "百"
        rest = value % 100
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + digits[rest]
        return head + _int_to_cn(rest)
    return str(value)


def parse_group_number(name: str) -> tuple[int, bool, bool] | None:
    """解析“第一组/第2组/3组”，返回 (序号, 是否有“第”, 是否中文数字)。"""
    matched = _GROUP_RE.match((name or "").strip())
    if matched is None:
        return None
    prefix = matched.group(1) is not None
    numeral = matched.group(2)
    if numeral.isdigit():
        value = int(numeral)
        return (value, prefix, False) if value > 0 else None
    value = _cn_to_int(numeral)
    if value is None or value <= 0:
        return None
    return value, prefix, True


def group_sort_key(name: str):
    """数字组名按序号排在前，普通组名按名称排在后面。"""
    parsed = parse_group_number(name)
    if parsed is None:
        return (1, 0, name)
    return (0, parsed[0], name)


def next_group_names(existing_names, count: int) -> list[str]:
    """按已有最大序号续号；没有数字组名时从“第一组”开始。"""
    parsed = [item for name in existing_names if (item := parse_group_number(name)) is not None]
    if parsed:
        number, prefix, chinese = max(parsed, key=lambda item: item[0])
    else:
        number, prefix, chinese = 0, True, True

    existing = set(existing_names)
    created: list[str] = []
    candidate = number + 1
    while len(created) < count:
        numeral = _int_to_cn(candidate) if chinese else str(candidate)
        name = f"{'第' if prefix else ''}{numeral}组"
        if name not in existing:
            created.append(name)
            existing.add(name)
        candidate += 1
    return created
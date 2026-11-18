"""学科口径：按学校用语“语数英物化生政史地体音美微”，兼容旧称。"""

SUBJECTS = [
    "语文",
    "数学",
    "英语",
    "物理",
    "化学",
    "生物",
    "政治",
    "历史",
    "地理",
    "体育",
    "音乐",
    "美术",
    "微机",
]

SUBJECT_ALIASES = {
    "语文": "语文",
    "数学": "数学",
    "英语": "英语",
    "物理": "物理",
    "化学": "化学",
    "生物": "生物",
    "政治": "政治",
    "道德与法治": "政治",
    "道法": "政治",
    "历史": "历史",
    "地理": "地理",
    "体育": "体育",
    "音乐": "音乐",
    "美术": "美术",
    "微机": "微机",
    "信息技术": "微机",
    "信息": "微机",
}


def normalize_subject(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return SUBJECT_ALIASES.get(raw, raw)


def subject_key(value: str | None) -> str:
    return normalize_subject(value) or "未设学科"
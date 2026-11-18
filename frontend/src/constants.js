export const SUBJECTS = ['语文', '数学', '英语', '物理', '化学', '生物', '政治', '历史', '地理', '体育', '音乐', '美术', '微机']
export const SUBJECT_ALIASES = { 道德与法治: '政治', 道法: '政治', 信息技术: '微机', 信息: '微机' }
export const GRADE_ORDER = ['七年级', '八年级', '九年级']
export const GRADE_ALIASES = {
  七年级: '七年级',
  初一: '七年级',
  '7年级': '七年级',
  初中一年级: '七年级',
  八年级: '八年级',
  初二: '八年级',
  '8年级': '八年级',
  初中二年级: '八年级',
  九年级: '九年级',
  初三: '九年级',
  '9年级': '九年级',
  初中三年级: '九年级'
}
const GRADE_KEYS = Object.keys(GRADE_ALIASES).sort((a, b) => b.length - a.length)

export function normalizeGrade(value) {
  const raw = (value || '').trim().replace(/\s/g, '')
  if (!raw) return ''
  if (GRADE_ALIASES[raw]) return GRADE_ALIASES[raw]
  const key = GRADE_KEYS.find((k) => raw.startsWith(k))
  return key ? GRADE_ALIASES[key] : raw
}

export function normalizeSubject(value) {
  const raw = (value || '').trim()
  return SUBJECT_ALIASES[raw] || raw
}

export function gradeOfClass(className) {
  const raw = (className || '').trim().replace(/\s/g, '')
  const key = GRADE_KEYS.find((k) => raw.startsWith(k))
  return key ? GRADE_ALIASES[key] : ''
}

export function gradeRankOfClass(className) {
  const i = GRADE_ORDER.indexOf(gradeOfClass(className))
  return i === -1 ? 99 : i
}

const CN_DIGITS = '零一二三四五六七八九'
const CN_VALUES = Object.fromEntries([...CN_DIGITS].map((char, index) => [char, index]))

export function chineseToInt(text) {
  const raw = String(text || '').trim()
  if (!raw) return 0
  if (/^\d+$/.test(raw)) return Number(raw)
  if (raw.includes('十')) {
    const [left, right] = raw.split('十')
    const tens = left ? CN_VALUES[left] || 0 : 1
    const ones = right ? CN_VALUES[right] || 0 : 0
    return tens * 10 + ones
  }
  return CN_VALUES[raw] || 0
}

export function classNoOf(className) {
  const match = (className || '').match(/([0-9]+|[一二三四五六七八九十]+)\s*班?\s*$/)
  return match ? chineseToInt(match[1]) : 0
}

export function shortClassName(className) {
  const match = (className || '').match(/([0-9]+|[一二三四五六七八九十]+)班\s*$/)
  return match ? match[0] : className
}

export function classSortKey(className) {
  return [gradeRankOfClass(className), classNoOf(className), className || '']
}

export const ROLE_LABELS = {
  admin: '校长/主任',
  subject_lead: '学科组长',
  head: '班主任',
  deputy: '副班主任',
  teacher: '任课教师'
}

export function roleLabel(key) {
  return ROLE_LABELS[key] || ROLE_LABELS.teacher
}
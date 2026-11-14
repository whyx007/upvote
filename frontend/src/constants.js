export const SUBJECTS = ['语文', '数学', '英语', '物理', '化学', '道德与法治', '历史', '地理', '生物', '体育', '音乐', '美术', '信息技术']
export const GRADE_ORDER = ['初一', '初二', '初三']

export function gradeOfClass(className) {
  return GRADE_ORDER.find((g) => className && className.startsWith(g)) || ''
}

export function gradeRankOfClass(className) {
  const i = GRADE_ORDER.indexOf(gradeOfClass(className))
  return i === -1 ? 99 : i
}

export const ROLE_LABELS = {
  admin: '管理员',
  head: '班主任',
  deputy: '副班主任',
  teacher: '教师'
}

export function roleLabel(key) {
  return ROLE_LABELS[key] || ROLE_LABELS.teacher
}
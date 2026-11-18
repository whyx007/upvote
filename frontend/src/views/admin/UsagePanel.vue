<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { downloadBlob } from '../../api'
import { GRADE_ORDER, SUBJECTS, gradeOfClass, normalizeSubject } from '../../constants'
import { useAuthStore } from '../../stores/auth'

const props = defineProps({
  mode: { type: String, default: 'admin' }
})

const auth = useAuthStore()
const loading = ref(false)
const period = ref('month')
const startDate = ref('')
const endDate = ref('')
const subject = ref('')
const grade = ref('')
const className = ref('')
const registry = ref([])
const report = ref(null)
const detail = ref(null)
const showDetail = ref(false)
const detailLoading = ref(false)

const isLead = computed(() => props.mode === 'lead')
const scopeText = computed(() => {
  if (isLead.value) return `本科目：${normalizeSubject(auth.teacher?.subject) || '未设学科'}`
  return '全校教师'
})

const classNames = computed(() => {
  const names = registry.value.map((c) => c.name)
  return names.filter((c) => !grade.value || gradeOfClass(c) === grade.value)
})

const subjectOptions = computed(() => {
  const list = [...SUBJECTS]
  if (isLead.value) {
    const own = normalizeSubject(auth.teacher?.subject)
    return own ? [own] : []
  }
  return list
})

function today(offset = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

function setPeriod(key) {
  period.value = key
  if (key === 'custom') {
    if (!startDate.value) startDate.value = today(-7)
    if (!endDate.value) endDate.value = today()
  }
  load()
}

function params() {
  const value = {
    period: period.value,
    subject: subject.value || undefined,
    grade: grade.value || undefined,
    class_name: className.value || undefined
  }
  if (period.value === 'custom') {
    value.start = startDate.value
    value.end = endDate.value
  }
  return value
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/stats/usage', { params: params() })
    report.value = data
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function openDetail(item) {
  showDetail.value = true
  detailLoading.value = true
  detail.value = { teacher: item, items: [] }
  try {
    const { data } = await api.get(`/stats/usage/${item.teacher_id}`, { params: params() })
    detail.value = { teacher: item, items: data.items }
  } catch {
    /* 拦截器已提示 */
  } finally {
    detailLoading.value = false
  }
}

function exportReport() {
  downloadBlob('/stats/usage/export', '教师使用统计.xlsx', params())
}

function fmtTime(value) {
  return value ? value.slice(0, 16).replace('T', ' ') : '—'
}

function onGradeChange() {
  if (className.value && grade.value && gradeOfClass(className.value) !== grade.value) className.value = ''
  load()
}

function onClassChange() {
  load()
}

onMounted(async () => {
  try {
    const { data } = await api.get('/classes/registry')
    registry.value = data.items
  } catch {
    /* 无班级数据也可统计 */
  }
  if (isLead.value) subject.value = normalizeSubject(auth.teacher?.subject) || ''
  await load()
})
</script>

<template>
  <div class="usage-panel">
    <div class="usage-hero">
      <div>
        <div class="usage-kicker">TEACHER INSIGHT</div>
        <div class="usage-title">{{ isLead ? '本科目使用统计' : '教师使用统计' }}</div>
        <div class="usage-sub">{{ scopeText }} · 按点赞发生时间统计</div>
      </div>
      <div class="usage-hero-icon">📊</div>
    </div>

    <div class="usage-filters">
      <div class="usage-periods">
        <button type="button" :class="{ active: period === 'week' }" @click="setPeriod('week')">本周</button>
        <button type="button" :class="{ active: period === 'month' }" @click="setPeriod('month')">本月</button>
        <button type="button" :class="{ active: period === 'custom' }" @click="setPeriod('custom')">自定义</button>
      </div>
      <template v-if="period === 'custom'">
        <input v-model="startDate" class="native-select" type="date" @change="load" />
        <span class="muted">至</span>
        <input v-model="endDate" class="native-select" type="date" @change="load" />
      </template>
      <select v-if="!isLead" v-model="subject" class="native-select" @change="load">
        <option value="">全部学科</option>
        <option v-for="s in subjectOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <select v-model="grade" class="native-select" @change="onGradeChange">
        <option value="">全部年级</option>
        <option v-for="g in GRADE_ORDER" :key="g" :value="g">{{ g }}</option>
      </select>
      <select v-model="className" class="native-select" @change="onClassChange">
        <option value="">全部班级</option>
        <option v-for="c in classNames" :key="c" :value="c">{{ c }}</option>
      </select>
      <van-button size="small" plain icon="down" @click="exportReport">导出</van-button>
    </div>

    <div v-if="report" class="usage-summary">
      <div class="usage-summary-card">
        <strong>{{ report.summary.total_likes }}</strong>
        <span>点赞总数</span>
      </div>
      <div class="usage-summary-card">
        <strong>{{ report.summary.active_teachers }}</strong>
        <span>活跃教师</span>
      </div>
      <div class="usage-summary-card">
        <strong>{{ report.summary.teacher_count }}</strong>
        <span>统计教师</span>
      </div>
      <div class="usage-summary-card range">
        <strong>{{ report.summary.start_date.slice(5) }} ~ {{ report.summary.end_date.slice(5) }}</strong>
        <span>统计区间</span>
      </div>
    </div>

    <van-loading v-if="loading" style="text-align: center; padding: 30px" />
    <template v-else-if="report">
      <div class="usage-list">
        <button
          v-for="item in report.items"
          :key="item.teacher_id"
          type="button"
          class="usage-row"
          :class="{ zero: !item.like_count }"
          @click="openDetail(item)"
        >
          <div class="usage-avatar">{{ item.name.slice(-2) }}</div>
          <div class="usage-person">
            <strong>{{ item.name }} <small>{{ item.employee_no }}</small></strong>
            <span>{{ item.subject || '未设学科' }} · {{ item.classes.join('、') || '未任教' }}</span>
          </div>
          <div class="usage-numbers">
            <strong>{{ item.like_count }}</strong>
            <span>{{ item.active_days }} 天 · {{ item.student_count }} 生</span>
          </div>
          <div class="usage-last">{{ fmtTime(item.last_like_at) }}</div>
        </button>
      </div>
      <van-empty v-if="!report.items.length" description="该范围内没有教师" />
    </template>

    <van-popup teleport="body" v-model:show="showDetail" position="bottom" round :style="{ maxHeight: '82%' }">
      <div class="usage-detail">
        <div class="usage-detail-head">
          <div>
            <div class="usage-kicker">DETAIL</div>
            <div class="usage-title">{{ detail?.teacher?.name }} 的点赞明细</div>
            <div class="usage-sub">{{ report?.summary.start_date }} 至 {{ report?.summary.end_date }}</div>
          </div>
          <button type="button" class="usage-close" @click="showDetail = false">×</button>
        </div>
        <van-loading v-if="detailLoading" style="text-align: center; padding: 24px" />
        <div v-else class="usage-detail-list">
          <div v-for="row in detail?.items || []" :key="row.id" class="usage-detail-row">
            <div class="usage-detail-icon">👍</div>
            <div class="usage-detail-info">
              <strong>{{ row.student_name }} <small>{{ row.student_no }}</small></strong>
              <span>{{ row.class_name }}<template v-if="row.group_name"> · {{ row.group_name }}</template></span>
            </div>
            <div class="usage-detail-time">{{ fmtTime(row.created_at) }}</div>
          </div>
          <van-empty v-if="!(detail?.items || []).length" description="该范围内没有点赞记录" />
        </div>
      </div>
    </van-popup>
  </div>
</template>
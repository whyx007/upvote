<script setup>
import { onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api, { downloadBlob } from '../../api'

const result = ref(null)
const batch = ref(null)
const history = ref([])
const uploading = ref(false)
const SHEET_NAMES = { students: '学生', teachers: '教师', groups: '小组', teaching: '任教' }

const SHEET_SPECS = [
  { name: '学生', columns: '学号（可空）、姓名*、班级*、级、性别', note: '一张“学生”表按班级列导入；也可每班一个 sheet（sheet 名=班级）或每班一个文件（文件名=班级，如：七年级一班.xlsx）' },
  { name: '教师', columns: '工号（可空）、姓名*、学科、手机号、初始密码、角色', note: '一张“教师”表按学科列导入；也可每学科一个 sheet/文件（学科名=语文等）' }
]

async function afterRead(payload) {
  const items = Array.isArray(payload) ? payload : [payload]
  uploading.value = true
  try {
    const fd = new FormData()
    for (const item of items) fd.append('files', item.file)
    const { data } = await api.post('/imports', fd)
    if (data.items) {
      batch.value = data
      result.value = data.summary
    } else {
      batch.value = null
      result.value = data
    }
    const okCount = data.items ? data.items.filter((x) => x.ok).length : items.length
    showToast(`导入完成：${okCount}/${items.length} 个文件`)
    loadHistory()
  } catch {
    /* 拦截器已提示 */
  } finally {
    uploading.value = false
  }
}

async function loadHistory() {
  const { data } = await api.get('/imports')
  history.value = data.items
}

function summaryText(summary) {
  return Object.entries(summary || {})
    .map(([key, stat]) => `${SHEET_NAMES[key] || key} 新增 ${stat.created} / 更新 ${stat.updated}`)
    .join(' · ')
}

/* 一键清除名单 */
const showClear = ref(false)
const clearPassword = ref('')
const clearText = ref('')
const clearing = ref(false)

function openClear() {
  clearPassword.value = ''
  clearText.value = ''
  showClear.value = true
}

async function beforeClearClose(action) {
  if (action !== 'confirm') return true
  if (!clearPassword.value) {
    showToast('请输入管理员密码')
    return false
  }
  if (clearText.value.trim() !== '清除名单') {
    showToast('请输入“清除名单”确认')
    return false
  }
  clearing.value = true
  try {
    const { data } = await api.post('/admin/clear-roster', {
      password: clearPassword.value,
      confirm: clearText.value.trim()
    })
    const c = data.counts || {}
    showToast(`已清除：学生 ${c.students || 0}、教师 ${c.teachers || 0}、班级 ${c.classes || 0}`)
    result.value = null
    batch.value = null
    clearPassword.value = ''
    clearText.value = ''
    await loadHistory()
    return true
  } catch {
    return false
  } finally {
    clearing.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <div style="padding: 16px">
    <van-button type="primary" plain block icon="down" @click="downloadBlob('/imports/template', '名单导入模板.xlsx')">
      下载 Excel 名单模板（含格式说明）
    </van-button>
    <div style="margin-top: 12px">
      <van-uploader :after-read="afterRead" accept=".xlsx" :disabled="uploading" multiple>
        <van-button type="warning" block icon="plus" :loading="uploading">一键导入 Excel 名单（可多选文件）</van-button>
      </van-uploader>
      <div class="muted" style="margin-top: 6px; text-align: center">按班一个文件时，文件名必须是班级名，如：七年级一班.xlsx</div>
    </div>
    <div style="margin-top: 10px">
      <van-button type="danger" plain block icon="delete-o" @click="openClear">一键清除名单（需管理员密码）</van-button>
    </div>

    <van-notice-bar style="margin-top: 12px" left-icon="info-o" wrapable text="学生/教师名单可一张表导入，也可按班级/学科分 sheet 或分文件导入；小组、任教关系请在网页设置，不用填 Excel。学生不填学号会自动生成，教师不填工号从 T001 起生成；默认密码 123456。" />

    <div class="section-title">Excel 名单属性</div>
    <div class="sheet-spec-list">
      <div v-for="s in SHEET_SPECS" :key="s.name" class="sheet-spec">
        <div class="sheet-spec-head"><strong>{{ s.name }}</strong><span>{{ s.columns }}</span></div>
        <div class="sheet-spec-note">{{ s.note }}</div>
      </div>
    </div>

    <div v-if="batch && batch.items" class="section-title">本次文件结果</div>
    <van-cell-group v-if="batch && batch.items" inset>
      <van-cell
        v-for="item in batch.items"
        :key="item.filename"
        :title="item.filename"
        :value="item.ok ? '成功' : '失败'"
        :label="item.ok ? summaryText(item.summary) : item.error"
      />
    </van-cell-group>

    <template v-if="result">
      <div class="section-title">本次导入汇总</div>
      <van-cell-group inset>
        <van-cell v-for="(stat, key) in result" :key="key" :title="SHEET_NAMES[key] || key" :value="`新增 ${stat.created} · 更新 ${stat.updated} · 错误 ${stat.errors.length}`" />
      </van-cell-group>
      <template v-for="(stat, key) in result" :key="'err-' + key">
        <van-cell v-for="e in stat.errors" :key="key + '-' + e.row + '-' + (e.sheet || '')" :title="`${SHEET_NAMES[key] || key}${e.sheet ? ' · ' + e.sheet : ''} 第 ${e.row} 行`" :label="e.message" icon="warning-o" />
      </template>
    </template>

    <div class="section-title">导入历史</div>
    <van-cell-group inset>
      <van-cell v-for="h in history" :key="h.id" :title="h.filename" :label="h.created_at ? h.created_at.replace('T', ' ').slice(0, 16) : ''" />
    </van-cell-group>

    <van-dialog
      v-model:show="showClear"
      teleport="body"
      title="一键清除名单"
      show-cancel-button
      :before-close="beforeClearClose"
      class="form-dialog"
    >
      <div class="clear-warning">
        将清除：学生、小组、班级、任教关系、非管理员教师、点赞与兑换记录、导入历史。<br />
        <b>学期、奖励目录和管理员账号会保留。</b> 此操作不可恢复，建议先备份数据库。
      </div>
      <van-field v-model="clearPassword" type="password" label="管理员密码" placeholder="请输入当前管理员密码" />
      <van-field v-model="clearText" label="确认文字" placeholder="请输入：清除名单" />
      <div v-if="clearing" class="muted" style="padding: 8px 16px">正在清除…</div>
    </van-dialog>
  </div>
</template>
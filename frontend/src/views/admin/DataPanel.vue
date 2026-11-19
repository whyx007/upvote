<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import api, { downloadBlob } from '../../api'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const summary = ref(null)

const showRestore = ref(false)
const restoreFile = ref(null)
const restorePassword = ref('')
const restoreConfirm = ref('')
const restoring = ref(false)

const showReset = ref(false)
const resetPassword = ref('')
const resetConfirm = ref('')
const resetting = ref(false)

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value) {
  return value ? value.slice(0, 16).replace('T', ' ') : '—'
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/admin/data/summary')
    summary.value = data
  } finally {
    loading.value = false
  }
}

function downloadBackup() {
  downloadBlob('/admin/data/backup', 'upvote-backup.db', undefined, { timeout: 0 })
}

function downloadExcel() {
  downloadBlob('/admin/data/export.xlsx', 'upvote-personnel-likes.xlsx')
}

function downloadAuto(item) {
  downloadBlob(`/admin/data/backups/${encodeURIComponent(item.name)}`, item.name, undefined, {
    timeout: 0
  })
}

function openRestore() {
  restoreFile.value = null
  restorePassword.value = ''
  restoreConfirm.value = ''
  showRestore.value = true
}

function afterRestoreRead(payload) {
  const file = Array.isArray(payload) ? payload[0]?.file : payload?.file
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.db')) {
    showToast('只能选择 .db 备份文件')
    return
  }
  restoreFile.value = file
  restorePassword.value = ''
  restoreConfirm.value = ''
  showRestore.value = true
}

async function beforeRestoreClose(action) {
  if (action !== 'confirm') return true
  if (!restoreFile.value) {
    showToast('请先选择 .db 备份文件')
    return false
  }
  if (!restorePassword.value) {
    showToast('请输入管理员密码')
    return false
  }
  if (restoreConfirm.value.trim() !== '恢复数据') {
    showToast('请输入“恢复数据”确认')
    return false
  }
  restoring.value = true
  try {
    const fd = new FormData()
    fd.append('file', restoreFile.value)
    fd.append('password', restorePassword.value)
    fd.append('confirm', restoreConfirm.value.trim())
    await api.post('/admin/data/restore', fd, { timeout: 0 })
    showToast('恢复完成，请重新登录')
    auth.logout()
    router.push('/login')
    return true
  } catch {
    return false
  } finally {
    restoring.value = false
  }
}

function openReset() {
  resetPassword.value = ''
  resetConfirm.value = ''
  showReset.value = true
}

async function beforeResetClose(action) {
  if (action !== 'confirm') return true
  if (!resetPassword.value) {
    showToast('请输入管理员密码')
    return false
  }
  if (resetConfirm.value.trim() !== '恢复出厂设置') {
    showToast('请输入“恢复出厂设置”确认')
    return false
  }
  resetting.value = true
  try {
    const { data } = await api.post('/admin/data/reset', {
      password: resetPassword.value,
      confirm: resetConfirm.value.trim()
    })
    const c = data.counts || {}
    showToast(`已清空：学生 ${c.students || 0}、教师 ${c.teachers || 0}、点赞 ${c.likes || 0}`)
    showReset.value = false
    await load()
    return true
  } catch {
    return false
  } finally {
    resetting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div style="padding-bottom: 24px">
    <van-loading v-if="loading && !summary" style="text-align: center; padding: 30px" />
    <template v-else-if="summary">
      <div class="stat-grid" style="padding: 16px">
        <div class="stat-card"><div class="num">{{ summary.counts.students }}</div><div class="label">学生</div></div>
        <div class="stat-card"><div class="num">{{ summary.counts.teachers }}</div><div class="label">教师</div></div>
        <div class="stat-card"><div class="num">{{ summary.counts.classes }}</div><div class="label">班级</div></div>
        <div class="stat-card"><div class="num">{{ summary.counts.likes }}</div><div class="label">有效点赞</div></div>
        <div class="stat-card"><div class="num">{{ summary.counts.redemptions }}</div><div class="label">有效兑换</div></div>
        <div class="stat-card"><div class="num">{{ formatSize(summary.database.size) }}</div><div class="label">数据库大小</div></div>
      </div>

      <div class="section-title">备份与导出</div>
      <div style="padding: 0 16px; display: grid; gap: 10px">
        <van-button type="primary" block icon="down" @click="downloadBackup">下载完整备份（.db）</van-button>
        <van-button type="warning" plain block icon="down" @click="downloadExcel">导出人员名单 + 学生点赞总数（Excel）</van-button>
      </div>

      <div class="section-title">自动备份</div>
      <van-cell-group inset>
        <van-cell
          title="周一至周五 23:30"
          :label="summary.backup.enabled ? `保留最近 ${summary.backup.keep} 份自动备份` : '自动备份已关闭'"
          :value="summary.backup.enabled ? formatTime(summary.backup.next_at) : '已关闭'"
        />
        <van-cell
          v-for="item in summary.backup.items"
          :key="item.name"
          :title="item.name"
          :label="`${formatSize(item.size)} · ${formatTime(item.created_at)}`"
          is-link
          @click="downloadAuto(item)"
        />
      </van-cell-group>
      <div v-if="!summary.backup.items.length" class="muted" style="padding: 8px 16px">还没有自动备份；到下一个工作日 23:30 会自动生成。</div>

      <div class="section-title">上传恢复</div>
      <div class="clear-warning">
        上传完整 `.db` 备份会替换当前全部数据（不是合并）。恢复前会自动备份当前数据库；恢复成功后需要重新登录。
      </div>
      <div style="padding: 0 16px">
        <van-uploader :after-read="afterRestoreRead" accept=".db" :max-count="1" :disabled="restoring">
          <van-button type="primary" plain block icon="upgrade">选择 .db 备份文件</van-button>
        </van-uploader>
      </div>

      <div class="section-title">恢复出厂设置</div>
      <div class="clear-warning">
        将清空：学生、班级、教师（当前管理员除外）、小组、任教关系、点赞、兑换、学期、奖励、导入历史。<br />
        <b>当前管理员账号会保留。</b> 此操作不可恢复；系统会先自动备份。
      </div>
      <div style="padding: 0 16px">
        <van-button type="danger" plain block icon="delete-o" @click="openReset">恢复出厂设置</van-button>
      </div>
    </template>

    <van-dialog
      v-model:show="showRestore"
      teleport="body"
      title="上传恢复数据"
      show-cancel-button
      :before-close="beforeRestoreClose"
      class="form-dialog"
    >
      <div class="clear-warning">
        将用所选 `.db` 备份替换当前数据库；恢复前会自动备份当前数据。恢复成功后需要重新登录。
      </div>
      <van-cell title="备份文件" :value="restoreFile ? restoreFile.name : '未选择'" />
      <van-field v-model="restorePassword" type="password" label="管理员密码" placeholder="请输入当前管理员密码" />
      <van-field v-model="restoreConfirm" label="确认文字" placeholder="请输入：恢复数据" />
      <div v-if="restoring" class="muted" style="padding: 8px 16px">正在恢复，请勿关闭页面…</div>
      <div v-if="!restoreFile" style="padding: 0 16px 10px">
        <van-uploader :after-read="afterRestoreRead" accept=".db" :max-count="1">
          <van-button size="small" plain type="primary">选择 .db 文件</van-button>
        </van-uploader>
      </div>
    </van-dialog>

    <van-dialog
      v-model:show="showReset"
      teleport="body"
      title="恢复出厂设置"
      show-cancel-button
      :before-close="beforeResetClose"
      class="form-dialog"
    >
      <div class="clear-warning">
        将清空学生、班级、教师（当前管理员除外）、小组、任教关系、点赞、兑换、学期、奖励、导入历史。<br />
        <b>当前管理员账号会保留。</b> 系统会先自动备份，但操作不可恢复。
      </div>
      <van-field v-model="resetPassword" type="password" label="管理员密码" placeholder="请输入当前管理员密码" />
      <van-field v-model="resetConfirm" label="确认文字" placeholder="请输入：恢复出厂设置" />
      <div v-if="resetting" class="muted" style="padding: 8px 16px">正在清空…</div>
    </van-dialog>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api from '../../api'

const emit = defineEmits(['done'])
const plan = ref(null)
const loading = ref(false)
const error = ref('')
const targetYear = ref(null)
const newGrade7Count = ref(null)
const showRun = ref(false)
const password = ref('')
const confirmText = ref('')
const running = ref(false)

async function loadPreview() {
  loading.value = true
  error.value = ''
  try {
    const params = {}
    if (targetYear.value) params.target_year = Number(targetYear.value)
    if (newGrade7Count.value !== null && newGrade7Count.value !== '') {
      params.new_grade7_count = Number(newGrade7Count.value)
    }
    const { data } = await api.get('/admin/promotion/preview', { params })
    plan.value = data
    targetYear.value = data.target_year
    newGrade7Count.value = data.new_grade7_count
  } catch (err) {
    error.value = err.response?.data?.detail || '预览失败'
  } finally {
    loading.value = false
  }
}

function openRun() {
  password.value = ''
  confirmText.value = ''
  showRun.value = true
}

async function beforeRunClose(action) {
  if (action !== 'confirm') return true
  if (!password.value) {
    showToast('请输入管理员密码')
    return false
  }
  if (confirmText.value.trim() !== '学年升级') {
    showToast('请输入“学年升级”确认')
    return false
  }
  running.value = true
  try {
    const { data } = await api.post('/admin/promotion/run', {
      password: password.value,
      confirm: confirmText.value.trim(),
      target_year: Number(targetYear.value),
      new_grade7_count: Number(newGrade7Count.value)
    })
    const count =
      (data.plan?.graduate?.length || 0) +
      (data.plan?.promote8?.length || 0) +
      (data.plan?.promote7?.length || 0)
    showToast(`学年升级完成：处理 ${count} 个班级`)
    showRun.value = false
    emit('done')
    await loadPreview()
    return true
  } catch {
    return false
  } finally {
    running.value = false
  }
}

onMounted(loadPreview)
</script>

<template>
  <div style="padding-bottom: 24px">
    <van-notice-bar
      left-icon="info-o"
      wrapable
      text="学年升级会：九年级停用并按届归档、八年级升九年级、七年级升八年级，再创建新七年级空班。任教关系、小组随班级保留；历史点赞按点赞时班级快照保留。"
    />

    <div style="padding: 12px 16px 4px; display: grid; gap: 8px">
      <van-field v-model.number="targetYear" type="digit" label="目标学年（开始年份）" placeholder="如：2027" />
      <van-field v-model.number="newGrade7Count" type="digit" label="新七年级班级数" placeholder="如：28" />
      <van-button size="small" type="warning" plain icon="replay" :loading="loading" @click="loadPreview">
        刷新预览
      </van-button>
    </div>

    <div v-if="error" class="clear-warning">{{ error }}</div>
    <van-loading v-if="loading" style="text-align: center; padding: 30px" />
    <template v-else-if="plan">
      <div class="section-title">升级预览 · {{ plan.target_label }}</div>

      <van-cell-group inset>
        <van-cell
          v-for="item in plan.graduate"
          :key="'g-' + item.old"
          :title="`${item.old} → ${item.new}`"
          :label="`学生 ${item.students} · 教师 ${item.teachers} · 小组 ${item.groups}`"
          value="毕业归档"
        />
        <van-cell
          v-for="item in plan.promote8"
          :key="'8-' + item.old"
          :title="`${item.old} → ${item.new}`"
          :label="`学生 ${item.students} · 教师 ${item.teachers} · 小组 ${item.groups}`"
          value="八 → 九"
        />
        <van-cell
          v-for="item in plan.promote7"
          :key="'7-' + item.old"
          :title="`${item.old} → ${item.new}`"
          :label="`学生 ${item.students} · 教师 ${item.teachers} · 小组 ${item.groups}`"
          value="七 → 八"
        />
      </van-cell-group>

      <div class="section-title">新七年级空班</div>
      <div class="clear-warning">
        {{ plan.new_grade7.length ? plan.new_grade7.join('、') : '不自动创建，升级后可手动建班或导入名单。' }}
      </div>

      <div v-if="plan.warnings.length" class="clear-warning">
        <div v-for="warning in plan.warnings" :key="warning">· {{ warning }}</div>
      </div>
      <div v-if="plan.errors.length" class="clear-warning">
        <b>暂不能执行：</b>
        <div v-for="item in plan.errors" :key="item">· {{ item }}</div>
      </div>

      <div style="padding: 0 16px">
        <van-button
          type="danger"
          block
          icon="exchange"
          :disabled="!!plan.errors.length || !plan.graduate.length && !plan.promote8.length && !plan.promote7.length && !plan.new_grade7.length"
          @click="openRun"
        >
          执行学年升级
        </van-button>
      </div>
    </template>

    <van-dialog
      v-model:show="showRun"
      teleport="body"
      title="确认执行学年升级"
      show-cancel-button
      :before-close="beforeRunClose"
      class="form-dialog"
    >
      <div class="clear-warning">
        将升级到 <b>{{ plan?.target_label }}</b>，涉及：
        九年级归档 {{ plan?.graduate?.length || 0 }} 个班、
        八升九 {{ plan?.promote8?.length || 0 }} 个班、
        七升八 {{ plan?.promote7?.length || 0 }} 个班、
        新建七年级 {{ plan?.new_grade7?.length || 0 }} 个班。<br />
        此操作不可自动撤销，请确认已完成备份。
      </div>
      <van-field v-model="password" type="password" label="管理员密码" placeholder="请输入当前管理员密码" />
      <van-field v-model="confirmText" label="确认文字" placeholder="请输入：学年升级" />
      <div v-if="running" class="muted" style="padding: 8px 16px">正在升级，请勿关闭页面…</div>
    </van-dialog>
  </div>
</template>
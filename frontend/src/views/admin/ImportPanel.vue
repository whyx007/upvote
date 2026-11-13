<script setup>
import { onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api, { downloadBlob } from '../../api'

const result = ref(null)
const history = ref([])
const uploading = ref(false)
const SHEET_NAMES = { students: '学生', teachers: '教师', groups: '小组', teaching: '任教' }

async function afterRead(file) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.file)
    const { data } = await api.post('/imports', fd)
    result.value = data
    showToast('导入完成')
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

onMounted(loadHistory)
</script>

<template>
  <div style="padding: 16px">
    <van-button type="primary" plain block icon="down" @click="downloadBlob('/imports/template', 'upvote_template.xlsx')">
      下载导入模板（学生/教师/小组/任教）
    </van-button>
    <div style="margin-top: 12px">
      <van-uploader :after-read="afterRead" accept=".xlsx" :disabled="uploading">
        <van-button type="warning" block icon="plus" :loading="uploading">上传 Excel 导入（支持零散增量）</van-button>
      </van-uploader>
    </div>
    <van-notice-bar style="margin-top: 12px" left-icon="info-o" wrapable text="按学号/工号幂等去重：重复导入只更新不重复；小组成员学号需先导入学生；教师默认密码 123456。" />

    <template v-if="result">
      <div class="section-title">本次导入结果</div>
      <van-cell-group inset>
        <van-cell v-for="(stat, key) in result" :key="key" :title="SHEET_NAMES[key] || key" :value="`新增 ${stat.created} · 更新 ${stat.updated} · 错误 ${stat.errors.length}`" />
      </van-cell-group>
      <template v-for="(stat, key) in result" :key="'err-' + key">
        <van-cell v-for="e in stat.errors" :key="key + '-' + e.row" :title="`${SHEET_NAMES[key] || key} 第 ${e.row} 行`" :label="e.message" icon="warning-o" />
      </template>
    </template>

    <div class="section-title">导入历史</div>
    <van-cell-group inset>
      <van-cell v-for="h in history" :key="h.id" :title="h.filename" :label="h.created_at ? h.created_at.replace('T', ' ').slice(0, 16) : ''" />
    </van-cell-group>
  </div>
</template>
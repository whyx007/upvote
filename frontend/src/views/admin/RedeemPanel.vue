<script setup>
import { onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'

const q = ref('')
const candidates = ref([])
const selected = ref(null)
const balance = ref(null)
const rewards = ref([])
const rewardId = ref(null)
const history = ref([])
const submitting = ref(false)

async function search() {
  const { data } = await api.get('/students', { params: { q: q.value, page_size: 10 } })
  candidates.value = data.items
}

async function selectStudent(s) {
  selected.value = s
  candidates.value = []
  q.value = `${s.name}（${s.student_no}）`
  const { data } = await api.get(`/classes/${encodeURIComponent(s.class_name)}/roster`)
  const row = data.items.find((x) => x.id === s.id)
  balance.value = row ? row.semester_balance : 0
}

async function loadRewards() {
  const { data } = await api.get('/rewards')
  rewards.value = data.items
}

async function loadHistory() {
  const { data } = await api.get('/redemptions', { params: { page_size: 20 } })
  history.value = data.items
}

async function redeem() {
  if (!selected.value || !rewardId.value) {
    showToast('请先选择学生和奖励')
    return
  }
  submitting.value = true
  try {
    const { data } = await api.post('/redemptions', { student_id: selected.value.id, reward_id: rewardId.value })
    balance.value = data.new_balance
    showToast(`兑换成功，剩余 ⭐${data.new_balance}`)
    loadHistory()
    loadRewards()
  } catch {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

async function cancel(r) {
  try {
    await showConfirmDialog({ title: '取消兑换', message: `确定取消 ${r.student_name} 的「${r.reward_name}」兑换？星灿币将退还。` })
    await api.post(`/redemptions/${r.id}/cancel`)
    showToast('已取消并退还')
    loadHistory()
    loadRewards()
    if (selected.value) selectStudent(selected.value)
  } catch {
    /* 取消或拦截器提示 */
  }
}

onMounted(() => {
  loadRewards()
  loadHistory()
})
</script>

<template>
  <div>
    <van-search v-model="q" placeholder="搜索学生姓名 / 学号" @search="search" @clear="candidates = []" />
    <van-cell-group v-if="candidates.length" inset>
      <van-cell v-for="s in candidates" :key="s.id" :title="`${s.name}（${s.student_no}）`" :label="s.class_name" is-link @click="selectStudent(s)" />
    </van-cell-group>

    <template v-if="selected">
      <van-cell title="当前学生" :value="`${selected.name} · 学期余额 ⭐${balance}`" />
      <div class="section-title">选择奖励</div>
      <van-radio-group v-model="rewardId">
        <van-cell-group inset>
          <van-cell v-for="r in rewards" :key="r.id" :title="r.name" :label="`库存：${r.stock === null ? '不限量' : r.stock}`" clickable @click="rewardId = r.id">
            <template #right>
              <span style="margin-right: 8px">⭐ {{ r.cost_coins }}</span>
              <van-radio :name="r.id" />
            </template>
          </van-cell>
        </van-cell-group>
      </van-radio-group>
      <div style="padding: 16px">
        <van-button type="warning" block round :loading="submitting" @click="redeem">确认兑换（当场扣分）</van-button>
      </div>
    </template>

    <div class="section-title">最近兑换</div>
    <van-cell-group inset>
      <van-cell v-for="r in history" :key="r.id" :title="`${r.student_name} · ${r.reward_name}`" :label="r.created_at.replace('T', ' ').slice(0, 16)" :value="`-⭐${r.cost_coins}${r.cancelled ? '（已取消）' : ''}`">
        <template #right>
          <van-button v-if="!r.cancelled" size="mini" plain type="danger" style="margin-left: 8px" @click="cancel(r)">取消</van-button>
        </template>
      </van-cell>
    </van-cell-group>
  </div>
</template>
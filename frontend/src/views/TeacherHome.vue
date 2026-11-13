<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api from '../api'
import UserMenu from '../components/UserMenu.vue'

const classes = ref([])
const className = ref('')
const showClassPicker = ref(false)
const roster = ref([])
const groups = ref([])
const recent = ref([])
const tab = ref('like')
const loading = ref(false)
const liking = ref(new Set())
const likingGroup = ref(new Set())

const classColumns = computed(() => classes.value.map((c) => ({ text: c, value: c })))
const ranked = computed(() => [...roster.value].sort((a, b) => b.semester_balance - a.semester_balance))

async function loadClasses() {
  const { data } = await api.get('/my/classes')
  classes.value = data
  if (!className.value && data.length) className.value = data[0]
}

async function loadRecent() {
  if (!className.value) return
  const { data } = await api.get('/likes/recent', { params: { class_name: className.value, limit: 10 } })
  recent.value = data.items
}

async function loadAll() {
  if (!className.value) {
    roster.value = []
    groups.value = []
    recent.value = []
    return
  }
  loading.value = true
  try {
    const [r, g] = await Promise.all([
      api.get(`/classes/${encodeURIComponent(className.value)}/roster`),
      api.get('/groups', { params: { class_name: className.value } })
    ])
    roster.value = r.data.items
    groups.value = g.data.items
    await loadRecent()
  } finally {
    loading.value = false
  }
}

async function likeStudent(s) {
  if (liking.value.has(s.id)) return
  liking.value.add(s.id)
  try {
    const { data } = await api.post('/likes', { target_type: 'student', target_id: s.id })
    s.semester_balance = data.likes[0].semester_balance
    s.total_balance += 1
    showToast(`👍 ${s.name} +1`)
    loadRecent()
  } catch {
    /* 拦截器已提示 */
  } finally {
    liking.value.delete(s.id)
  }
}

async function likeGroup(g) {
  if (likingGroup.value.has(g.id)) return
  likingGroup.value.add(g.id)
  try {
    const { data } = await api.post('/likes', { target_type: 'group', target_id: g.id })
    for (const l of data.likes) {
      const s = roster.value.find((x) => x.id === l.student_id)
      if (s) {
        s.semester_balance = l.semester_balance
        s.total_balance += 1
      }
    }
    showToast(`👍 ${g.name} 全员 +1`)
    loadRecent()
  } catch {
    /* 拦截器已提示 */
  } finally {
    likingGroup.value.delete(g.id)
  }
}

async function undo(item) {
  try {
    await api.post('/likes/revoke', { batch_id: item.batch_id })
    showToast('已撤销')
    loadAll()
  } catch {
    /* 拦截器已提示 */
  }
}

function onClassConfirm({ selectedValues }) {
  className.value = selectedValues[0]
  showClassPicker.value = false
  loadAll()
}

function fmtTime(iso) {
  return iso ? iso.slice(11, 16) : ''
}

onMounted(async () => {
  await loadClasses()
  await loadAll()
})
</script>

<template>
  <div class="page">
    <van-nav-bar title="星灿点赞" fixed placeholder>
      <template #right><UserMenu /></template>
    </van-nav-bar>

    <van-cell title="班级" :value="className || '未分配'" is-link @click="showClassPicker = true" />

    <van-tabs v-model:active="tab" sticky>
      <van-tab title="点赞" name="like">
        <van-loading v-if="loading" style="text-align: center; padding: 24px" />
        <template v-else>
          <van-empty v-if="!className" description="还没有任教班级，请联系管理员导入任教关系" />
          <template v-else>
            <template v-if="groups.length">
              <div class="section-title">学习小组（一键全员点赞）</div>
              <div class="group-row">
                <div v-for="g in groups" :key="g.id" class="group-chip">
                  <span>{{ g.name }}（{{ g.member_count }}人）</span>
                  <van-button size="small" type="warning" round :loading="likingGroup.has(g.id)" @click="likeGroup(g)">👍</van-button>
                </div>
              </div>
            </template>
            <div class="section-title">学生（{{ roster.length }} 人）· 点 👍 即 +1 星灿币</div>
            <van-empty v-if="!roster.length" description="该班级还没有学生，请先导入" />
            <div class="student-grid">
              <div v-for="s in roster" :key="s.id" class="student-card">
                <div class="name">{{ s.name }}</div>
                <div class="no">{{ s.student_no }}</div>
                <div class="coin-badge">⭐ {{ s.semester_balance }}</div>
                <van-button class="like-btn" type="warning" round :loading="liking.has(s.id)" @click="likeStudent(s)">👍</van-button>
              </div>
            </div>
            <template v-if="recent.length">
              <div class="section-title">最近点赞（当日可撤销）</div>
              <van-cell-group inset>
                <van-cell v-for="item in recent" :key="item.batch_id" :title="item.student_names.join('、') + (item.group_name ? `〔${item.group_name}〕` : '')" :label="`${fmtTime(item.created_at)} · ${item.count} 赞${item.revoked ? ' · 已撤销' : ''}`">
                  <template #right>
                    <van-button v-if="item.can_revoke" size="mini" plain type="danger" @click="undo(item)">撤销</van-button>
                  </template>
                </van-cell>
              </van-cell-group>
            </template>
          </template>
        </template>
      </van-tab>
      <van-tab title="排行" name="rank">
        <van-cell-group inset style="margin-top: 12px">
          <van-cell v-for="(s, i) in ranked" :key="s.id" :title="`${i + 1}. ${s.name}`" :label="s.student_no" :value="`⭐ ${s.semester_balance}（累计 ${s.total_balance}）`" />
        </van-cell-group>
      </van-tab>
    </van-tabs>

    <van-popup v-model:show="showClassPicker" position="bottom" round>
      <van-picker :columns="classColumns" @confirm="onClassConfirm" @cancel="showClassPicker = false" />
    </van-popup>
  </div>
</template>
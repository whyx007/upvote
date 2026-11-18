<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api from '../api'
import UserMenu from '../components/UserMenu.vue'
import ClassWorkspace from './admin/ClassWorkspace.vue'
import UsagePanel from './admin/UsagePanel.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const classes = ref([])
const className = ref('')
const semester = ref(null)
const managedRoles = ref([])
const showClassPicker = ref(false)
const roster = ref([])
const groups = ref([])
const recent = ref([])
const tab = ref('like')
const loading = ref(false)
const liking = ref(new Set())
const likingGroup = ref(new Set())
const search = ref('')
const myUsage = ref(null)

// 顶部身份：管理员 > 当前班级角色 > 学科组长 > 普通教师
const roleKey = computed(() => {
  if (auth.isAdmin) return 'admin'
  const hit = managedRoles.value.find((r) => r.class_name === className.value)
  if (hit) return hit.duty
  if (auth.isSubjectLead) return 'subject_lead'
  return 'teacher'
})
const ranked = computed(() => [...roster.value].sort((a, b) => b.semester_balance - a.semester_balance || a.student_no.localeCompare(b.student_no)))
const visibleRoster = computed(() => {
  const q = search.value.trim()
  return q ? roster.value.filter((s) => s.name.includes(q) || s.student_no.includes(q)) : roster.value
})
const classCoins = computed(() => roster.value.reduce((sum, s) => sum + s.semester_balance, 0))
const myWeek = computed(() => {
  const items = myUsage.value?.items || []
  return items.find((x) => x.teacher_id === auth.teacher?.id) || items[0] || null
})

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

async function loadMyUsage() {
  try {
    const { data } = await api.get('/stats/usage', { params: { period: 'week' } })
    myUsage.value = data
  } catch {
    myUsage.value = null
  }
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
    loadMyUsage()
  } catch {
    /* 拦截器已提示 */
  } finally {
    liking.value.delete(s.id)
  }
}

async function decrementStudent(s) {
  if (liking.value.has(s.id) || s.semester_balance <= 0) return
  liking.value.add(s.id)
  try {
    const { data } = await api.post('/likes/decrement', { student_id: s.id })
    s.semester_balance = data.semester_balance
    s.total_balance = data.total_balance
    showToast(`${s.name} −1，已回退最近一次点赞`)
    loadRecent()
    loadMyUsage()
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
    loadMyUsage()
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

function selectClass(c) {
  className.value = c
  showClassPicker.value = false
  search.value = ''
  loadAll()
}

function fmtTime(iso) {
  return iso ? iso.slice(11, 16) : ''
}

function avatarText(name) {
  return name.length > 2 ? name.slice(-2) : name
}

onMounted(async () => {
  const [semesterResponse, , rolesResponse] = await Promise.all([
    api.get('/semesters/current'),
    loadClasses(),
    api.get('/my/class-roles')
  ])
  semester.value = semesterResponse.data
  managedRoles.value = rolesResponse.data.items
  await Promise.all([loadAll(), loadMyUsage()])
})
</script>

<template>
  <div class="page teacher-page">
    <van-nav-bar class="teacher-nav" title="星灿点赞" fixed placeholder>
      <template #right><UserMenu :role-key="roleKey" /></template>
    </van-nav-bar>

    <section class="class-hero">
      <div class="hero-orb hero-orb-a"></div>
      <div class="hero-orb hero-orb-b"></div>
      <div class="hero-content">
        <div class="hero-kicker"><span>✦</span> 星灿币 · 让每一点进步被看见</div>
        <div class="hero-class-row">
          <button class="hero-class" type="button" @click="showClassPicker = true">
            <span>{{ className || '选择任教班级' }}</span>
            <van-icon name="arrow-down" class="hero-class-icon" />
          </button>
        </div>
        <div class="hero-meta">{{ semester ? semester.name : '尚未激活学期' }}</div>
        <div v-if="myWeek" class="hero-week">本周 · 👍 {{ myWeek.like_count }} 次 · 使用 {{ myWeek.active_days }} 天</div>
        <div class="hero-stats">
          <div><strong>{{ roster.length }}</strong><span>班级学生</span></div>
          <i></i>
          <div><strong>{{ groups.length }}</strong><span>学习小组</span></div>
          <i></i>
          <div><strong>{{ classCoins }}</strong><span>本学期星灿币</span></div>
        </div>
      </div>
    </section>

    <van-tabs v-model:active="tab" class="teacher-tabs" animated swipeable>
      <van-tab title="课堂点赞" name="like">
        <van-loading v-if="loading" style="text-align: center; padding: 40px" />
        <template v-else>
          <van-empty v-if="!className" description="还没有任教班级，请联系管理员导入任教关系" />
          <template v-else>
            <section v-if="groups.length" class="like-section group-section">
              <div class="section-heading">
                <div><span class="section-eyebrow">TEAM SPIRIT</span><h3>为小组喝彩</h3></div>
                <span class="section-tip">一键全组 +1</span>
              </div>
              <div class="group-row">
                <div v-for="(g, index) in groups" :key="g.id" class="group-chip" :class="`tone-${index % 4}`">
                  <div class="group-icon">✦</div>
                  <div class="group-info"><strong>{{ g.name }}</strong><span>{{ g.member_count }} 位成员</span></div>
                  <van-button size="small" round :loading="likingGroup.has(g.id)" @click="likeGroup(g)">👍 +1</van-button>
                </div>
              </div>
            </section>

            <section class="like-section students-section">
              <div class="section-heading">
                <div><span class="section-eyebrow">EVERY STAR COUNTS</span><h3>为学生点赞 <em>{{ roster.length }}</em></h3></div>
                <span class="section-tip">👍 加 1 · − 减 1</span>
              </div>
              <van-search v-model="search" class="student-search" placeholder="快速找学生：姓名 / 学号" shape="round" background="transparent" />
              <van-empty v-if="!roster.length" description="该班级还没有学生，请先导入" />
              <van-empty v-else-if="!visibleRoster.length" description="没有匹配的学生" />
              <div class="student-grid">
                <div v-for="s in visibleRoster" :key="s.id" class="student-card" :class="{ 'has-coins': s.semester_balance > 0 }">
                  <div class="student-avatar" :class="s.gender === '女' ? 'girl' : 'boy'">{{ avatarText(s.name) }}</div>
                  <div class="student-name">{{ s.name }}</div>
                  <div class="student-no">{{ s.student_no }}</div>
                  <div class="student-balance"><span>⭐</span><strong>{{ s.semester_balance }}</strong><small>星灿币</small></div>
                  <div class="like-controls">
                    <button
                      class="decrement-btn"
                      type="button"
                      :disabled="s.semester_balance <= 0 || liking.has(s.id)"
                      :aria-label="`减少${s.name}一个点赞`"
                      @click="decrementStudent(s)"
                    >−</button>
                    <van-button class="like-btn" type="warning" round :loading="liking.has(s.id)" @click="likeStudent(s)">
                      <span class="like-symbol">👍</span><span class="like-plus">+1</span>
                    </van-button>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="recent.length" class="like-section recent-section">
              <div class="section-heading">
                <div><span class="section-eyebrow">JUST NOW</span><h3>最近点赞</h3></div>
                <span class="section-tip">当日可撤销</span>
              </div>
              <div class="recent-list">
                <div v-for="item in recent" :key="item.batch_id" class="recent-item" :class="{ revoked: item.revoked }">
                  <div class="recent-icon">👍</div>
                  <div class="recent-info">
                    <strong>{{ item.student_names.join('、') }}<span v-if="item.group_name">〔{{ item.group_name }}〕</span></strong>
                    <span>{{ fmtTime(item.created_at) }} · {{ item.count }} 赞{{ item.revoked ? ' · 已撤销' : '' }}</span>
                  </div>
                  <van-button v-if="item.can_revoke" size="mini" plain type="danger" round @click="undo(item)">撤销</van-button>
                </div>
              </div>
            </section>
          </template>
        </template>
      </van-tab>

      <van-tab title="班级星光榜" name="rank">
        <section class="like-section rank-section">
          <div class="section-heading">
            <div><span class="section-eyebrow">SHINING STARS</span><h3>班级星光榜</h3></div>
            <span class="section-tip">按本学期星灿币排序</span>
          </div>
          <div class="rank-list">
            <div v-for="(s, i) in ranked" :key="s.id" class="rank-row" :class="{ 'rank-top': i < 3 }">
              <div class="rank-number">{{ i + 1 }}</div>
              <div class="student-avatar small" :class="s.gender === '女' ? 'girl' : 'boy'">{{ avatarText(s.name) }}</div>
              <div class="rank-person"><strong>{{ s.name }}</strong><span>{{ s.student_no }}</span></div>
              <div class="rank-coins"><strong>⭐ {{ s.semester_balance }}</strong><span>累计 {{ s.total_balance }}</span></div>
            </div>
          </div>
          <van-empty v-if="!ranked.length" description="暂无排行数据" />
        </section>
      </van-tab>

      <van-tab v-if="auth.isSubjectLead" title="小组管理" name="groups">
        <ClassWorkspace groups-only />
      </van-tab>

      <van-tab v-if="managedRoles.length" title="班级管理" name="manage">
        <ClassWorkspace managed-only />
      </van-tab>

      <van-tab v-if="auth.isSubjectLead" title="使用统计" name="usage">
        <UsagePanel mode="lead" />
      </van-tab>
    </van-tabs>

    <van-popup teleport="body" v-model:show="showClassPicker" position="bottom" round>
      <div class="class-picker-panel">
        <div class="class-picker-title">选择班级</div>
        <div class="class-picker-list">
          <button
            v-for="c in classes"
            :key="c"
            type="button"
            class="class-picker-item"
            :class="{ active: c === className }"
            @click="selectClass(c)"
          >
            <span>{{ c }}</span>
            <van-icon v-if="c === className" name="success" />
          </button>
          <van-empty v-if="!classes.length" description="还没有任教班级" />
        </div>
      </div>
    </van-popup>
  </div>
</template>
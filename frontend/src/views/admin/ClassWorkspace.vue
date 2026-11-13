<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'
import MemberPicker from '../../components/MemberPicker.vue'
import { GRADE_ORDER, gradeOfClass } from '../../constants'

const classes = ref([])
const className = ref('')
const showClassPopup = ref(false)
const tab = ref('students')
const roster = ref([])
const groups = ref([])
const classTeachers = ref([])
const studentSearch = ref('')
const loading = ref(false)

const groupedClasses = computed(() => {
  const map = {}
  for (const c of classes.value) {
    const g = gradeOfClass(c) || '其他'
    ;(map[g] = map[g] || []).push(c)
  }
  return [...GRADE_ORDER, '其他'].filter((g) => map[g]).map((g) => ({ grade: g, classes: map[g] }))
})

const filteredRoster = computed(() => {
  const q = studentSearch.value.trim()
  if (!q) return roster.value
  return roster.value.filter((s) => s.name.includes(q) || s.student_no.includes(q))
})

async function loadClasses() {
  const { data } = await api.get('/classes')
  classes.value = data
  if (!className.value && data.length) className.value = data[0]
}

async function loadClassData() {
  if (!className.value) return
  loading.value = true
  try {
    const [r, g, t] = await Promise.all([
      api.get(`/classes/${encodeURIComponent(className.value)}/roster`),
      api.get('/groups', { params: { class_name: className.value, include_members: 1 } }),
      api.get(`/classes/${encodeURIComponent(className.value)}/teachers`)
    ])
    roster.value = r.data.items
    groups.value = g.data.items
    classTeachers.value = t.data.items
  } finally {
    loading.value = false
  }
}

function selectClass(c) {
  className.value = c
  showClassPopup.value = false
  studentSearch.value = ''
  loadClassData()
}

/* ---------- 学生 ---------- */
const showStudentDialog = ref(false)
const editingStudent = ref(null)
const studentForm = ref({ student_no: '', name: '', grade: '', enrollment_year: null })

function openStudentCreate() {
  editingStudent.value = null
  studentForm.value = { student_no: '', name: '', grade: gradeOfClass(className.value), enrollment_year: null }
  showStudentDialog.value = true
}

function openStudentEdit(s) {
  editingStudent.value = s
  studentForm.value = { student_no: s.student_no, name: s.name, grade: s.grade || '', enrollment_year: s.enrollment_year }
  showStudentDialog.value = true
}

async function saveStudent() {
  try {
    const body = { ...studentForm.value, class_name: className.value }
    if (editingStudent.value) {
      await api.patch(`/students/${editingStudent.value.id}`, body)
    } else {
      await api.post('/students', body)
    }
    showToast('已保存')
    showStudentDialog.value = false
    loadClassData()
    loadClasses()
  } catch {
    /* 拦截器已提示 */
  }
}

async function removeStudent(s) {
  try {
    await showConfirmDialog({ title: '删除学生', message: `确定删除 ${s.name}？（停用，重新导入可恢复）` })
    await api.delete(`/students/${s.id}`)
    showToast('已删除')
    loadClassData()
  } catch {
    /* 取消或拦截器提示 */
  }
}

/* ---------- 小组 ---------- */
const showGroupDialog = ref(false)
const editingGroup = ref(null)
const groupName = ref('')
const pickerShow = ref(false)
const pickerGroup = ref(null)
const pickerSelected = ref([])

function openGroupCreate() {
  editingGroup.value = null
  groupName.value = ''
  showGroupDialog.value = true
}

function openGroupRename(g) {
  editingGroup.value = g
  groupName.value = g.name
  showGroupDialog.value = true
}

async function saveGroup() {
  if (!groupName.value.trim()) {
    showToast('请输入小组名称')
    return
  }
  try {
    if (editingGroup.value) {
      await api.patch(`/groups/${editingGroup.value.id}`, { name: groupName.value.trim() })
      showToast('已保存')
      showGroupDialog.value = false
      loadClassData()
    } else {
      const { data } = await api.post('/groups', {
        name: groupName.value.trim(),
        class_name: className.value,
        member_student_nos: []
      })
      showGroupDialog.value = false
      await loadClassData()
      const created = groups.value.find((g) => g.id === data.id)
      if (created) openMemberPicker(created)
    }
  } catch {
    /* 拦截器已提示 */
  }
}

function openMemberPicker(g) {
  pickerGroup.value = g
  pickerSelected.value = (g.members || []).map((m) => m.id)
  pickerShow.value = true
}

async function onPickerConfirm(ids) {
  try {
    const nos = roster.value.filter((s) => ids.includes(s.id)).map((s) => s.student_no)
    await api.patch(`/groups/${pickerGroup.value.id}`, { member_student_nos: nos })
    pickerShow.value = false
    showToast('成员已更新')
    loadClassData()
  } catch {
    /* 拦截器已提示 */
  }
}

async function removeGroup(g) {
  try {
    await showConfirmDialog({ title: '删除小组', message: `确定删除「${g.name}」？历史点赞记录保留。` })
    await api.delete(`/groups/${g.id}`)
    showToast('已删除')
    loadClassData()
  } catch {
    /* 取消或拦截器提示 */
  }
}

/* ---------- 任课教师 ---------- */
const showAssignDialog = ref(false)
const allTeachers = ref([])
const teacherSearch = ref('')

async function openAssign() {
  try {
    const { data } = await api.get('/teachers', { params: { page_size: 500 } })
    allTeachers.value = data.items.filter((t) => t.is_active)
    teacherSearch.value = ''
    showAssignDialog.value = true
  } catch {
    /* 拦截器已提示 */
  }
}

const assignedIds = computed(() => new Set(classTeachers.value.map((t) => t.id)))
const assignCandidates = computed(() => {
  const q = teacherSearch.value.trim()
  return allTeachers.value.filter(
    (t) => !q || t.name.includes(q) || t.employee_no.includes(q) || (t.subject || '').includes(q)
  )
})

async function assignTeacher(t) {
  try {
    await api.post(`/classes/${encodeURIComponent(className.value)}/teachers`, { teacher_id: t.id })
    showToast(`${t.name} 已任教本班`)
    showAssignDialog.value = false
    loadClassData()
  } catch {
    /* 拦截器已提示 */
  }
}

async function removeClassTeacher(t) {
  try {
    await showConfirmDialog({ title: '移除任课', message: `确定移除 ${t.name} 在本班的任课？（不删除教师账号）` })
    await api.delete(`/classes/${encodeURIComponent(className.value)}/teachers/${t.id}`)
    showToast('已移除')
    loadClassData()
  } catch {
    /* 取消或拦截器提示 */
  }
}

onMounted(async () => {
  await loadClasses()
  await loadClassData()
})
</script>

<template>
  <div class="class-workspace">
    <aside class="class-nav">
      <div class="nav-title">班级导航</div>
      <div v-for="g in groupedClasses" :key="g.grade" class="nav-grade">
        <div class="nav-grade-title">{{ g.grade }}</div>
        <div class="nav-class-grid">
          <button
            v-for="c in g.classes"
            :key="c"
            class="nav-class"
            :class="{ active: c === className }"
            @click="selectClass(c)"
          >
            {{ c.replace(g.grade, '') }}
          </button>
        </div>
      </div>
    </aside>

    <main class="class-main">
      <van-cell class="class-switch" :title="`班级：${className || '未选择'}`" is-link @click="showClassPopup = true" />
      <div class="class-header">
        <h3>{{ className || '请先在左侧选择班级' }}</h3>
        <span class="muted">{{ roster.length }} 名学生 · {{ groups.length }} 个小组 · {{ classTeachers.length }} 位任课教师</span>
      </div>

      <van-tabs v-model:active="tab" sticky>
        <van-tab :title="`学生 ${roster.length}`" name="students">
          <div class="toolbar">
            <van-search v-model="studentSearch" placeholder="搜索姓名 / 学号" style="flex: 1" />
            <van-button size="small" type="warning" icon="plus" @click="openStudentCreate">新增学生</van-button>
          </div>
          <van-loading v-if="loading" style="text-align: center; padding: 24px" />
          <div v-else class="roster-list">
            <div v-for="s in filteredRoster" :key="s.id" class="roster-row">
              <div class="roster-info">
                <div class="roster-name">{{ s.name }} <span class="roster-no">{{ s.student_no }}</span></div>
                <div class="roster-tags">
                  <van-tag v-for="gname in s.groups" :key="gname" plain type="warning" size="medium">{{ gname }}</van-tag>
                  <span v-if="!s.groups.length" class="muted">未分组</span>
                </div>
              </div>
              <div class="roster-actions">
                <van-button size="mini" plain type="primary" icon="edit" @click="openStudentEdit(s)" />
                <van-button size="mini" plain type="danger" icon="delete-o" @click="removeStudent(s)" />
              </div>
            </div>
            <van-empty v-if="!filteredRoster.length" description="没有学生" />
          </div>
        </van-tab>

        <van-tab :title="`小组 ${groups.length}`" name="groups">
          <div class="toolbar">
            <van-button size="small" type="warning" icon="plus" @click="openGroupCreate">新增小组</van-button>
            <span class="muted">同一学生可加入多个小组</span>
          </div>
          <div class="group-cards">
            <div v-for="g in groups" :key="g.id" class="group-card">
              <div class="group-card-head">
                <b>{{ g.name }}</b>
                <van-tag type="warning" plain size="medium">{{ g.member_count }} 人</van-tag>
                <div class="spacer"></div>
                <van-button size="mini" type="warning" plain @click="openMemberPicker(g)">管理成员</van-button>
                <van-button size="mini" plain icon="edit" @click="openGroupRename(g)" />
                <van-button size="mini" plain type="danger" icon="delete-o" @click="removeGroup(g)" />
              </div>
              <div class="group-members">
                <van-tag v-for="m in g.members" :key="m.id" size="medium" class="member-chip">{{ m.name }}</van-tag>
                <span v-if="!g.members || !g.members.length" class="muted">暂无成员，点「管理成员」勾选添加</span>
              </div>
            </div>
            <van-empty v-if="!groups.length" description="还没有小组，点「新增小组」创建并勾选成员" />
          </div>
        </van-tab>

        <van-tab :title="`教师 ${classTeachers.length}`" name="teachers">
          <div class="toolbar">
            <van-button size="small" type="warning" icon="plus" @click="openAssign">指派教师</van-button>
            <span class="muted">移除任课不会删除教师账号</span>
          </div>
          <div class="roster-list">
            <div v-for="t in classTeachers" :key="t.id" class="roster-row">
              <div class="roster-info">
                <div class="roster-name">{{ t.name }} <span class="roster-no">{{ t.employee_no }}</span></div>
                <div class="roster-tags">
                  <van-tag type="primary" plain size="medium">{{ t.subject || '未设学科' }}</van-tag>
                </div>
              </div>
              <div class="roster-actions">
                <van-button size="mini" plain type="danger" @click="removeClassTeacher(t)">移除</van-button>
              </div>
            </div>
            <van-empty v-if="!classTeachers.length" description="还没有任课教师，点「指派教师」添加" />
          </div>
        </van-tab>
      </van-tabs>
    </main>

    <!-- 窄屏班级选择 -->
    <van-popup v-model:show="showClassPopup" position="left" :style="{ width: '70%', height: '100%' }">
      <div style="padding: 16px">
        <div v-for="g in groupedClasses" :key="g.grade" class="nav-grade">
          <div class="nav-grade-title">{{ g.grade }}</div>
          <div class="nav-class-grid">
            <button
              v-for="c in g.classes"
              :key="c"
              class="nav-class"
              :class="{ active: c === className }"
              @click="selectClass(c)"
            >
              {{ c.replace(g.grade, '') }}
            </button>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- 学生编辑 -->
    <van-dialog v-model:show="showStudentDialog" :title="editingStudent ? '编辑学生' : `新增学生 · ${className}`" show-cancel-button class="form-dialog" @confirm="saveStudent">
      <van-field v-model="studentForm.student_no" label="学号" placeholder="必填，唯一" :disabled="!!editingStudent" />
      <van-field v-model="studentForm.name" label="姓名" placeholder="必填" />
      <van-field :model-value="className" label="班级" disabled />
      <van-field v-model="studentForm.grade" label="年级" placeholder="如：初一" />
      <van-field v-model.number="studentForm.enrollment_year" label="入学年份" type="digit" placeholder="如：2026" />
    </van-dialog>

    <!-- 小组名称 -->
    <van-dialog v-model:show="showGroupDialog" :title="editingGroup ? '小组改名' : `新增小组 · ${className}`" show-cancel-button class="form-dialog" @confirm="saveGroup">
      <van-field v-model="groupName" label="小组名称" placeholder="如：星辰组" />
      <div v-if="!editingGroup" class="muted" style="padding: 8px 16px">创建后将自动打开成员勾选器</div>
    </van-dialog>

    <!-- 成员勾选器 -->
    <MemberPicker
      v-model:show="pickerShow"
      :title="`管理成员 · ${pickerGroup ? pickerGroup.name : ''}`"
      :students="roster"
      :selected="pickerSelected"
      @confirm="onPickerConfirm"
    />

    <!-- 指派教师 -->
    <van-dialog v-model:show="showAssignDialog" :title="`指派教师到 ${className}`" :show-confirm-button="false" class="form-dialog">
      <van-search v-model="teacherSearch" placeholder="搜索姓名 / 工号 / 学科" />
      <div class="assign-list">
        <van-cell
          v-for="t in assignCandidates"
          :key="t.id"
          :title="`${t.name}（${t.employee_no}）${assignedIds.has(t.id) ? ' · 已任教本班' : ''}`"
          :label="`${t.subject || '未设学科'} · ${(t.classes || []).join('、') || '暂无任教'}`"
          :is-link="!assignedIds.has(t.id)"
          @click="assignTeacher(t)"
        />
        <van-empty v-if="!assignCandidates.length" description="没有匹配的教师" />
      </div>
    </van-dialog>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'
import { SUBJECTS, GRADE_ORDER, gradeOfClass } from '../../constants'

const teachers = ref([])
const allClasses = ref([])
const q = ref('')
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ employee_no: '', name: '', phone: '', role: 'teacher', subject: '', password: '', classes: [] })
const showSubjectPicker = ref(false)
const subjectColumns = SUBJECTS.map((s) => ({ text: s, value: s }))

async function load() {
  const { data } = await api.get('/teachers', { params: { page_size: 500 } })
  teachers.value = data.items
}

async function loadClasses() {
  const { data } = await api.get('/classes')
  allClasses.value = data
}

const classOptions = computed(() => {
  const map = {}
  for (const c of allClasses.value) {
    const g = gradeOfClass(c) || '其他'
    ;(map[g] = map[g] || []).push(c)
  }
  return [...GRADE_ORDER, '其他'].filter((g) => map[g]).map((g) => ({ grade: g, classes: map[g] }))
})

function toggleClass(c) {
  const i = form.value.classes.indexOf(c)
  if (i >= 0) form.value.classes.splice(i, 1)
  else form.value.classes.push(c)
}

const filtered = computed(() =>
  teachers.value.filter(
    (t) => !q.value || t.name.includes(q.value) || t.employee_no.includes(q.value) || (t.subject || '').includes(q.value)
  )
)

function gradeRank(t) {
  const ranks = (t.classes || []).map((c) => GRADE_ORDER.indexOf(gradeOfClass(c))).filter((i) => i >= 0)
  return ranks.length ? Math.min(...ranks) : 99
}

function gradeLabel(t) {
  const gs = [...new Set((t.classes || []).map(gradeOfClass).filter(Boolean))]
  gs.sort((a, b) => GRADE_ORDER.indexOf(a) - GRADE_ORDER.indexOf(b))
  return gs.join('/') || '未任教'
}

const grouped = computed(() => {
  const bySubject = {}
  for (const t of filtered.value) {
    const s = t.subject || '未设学科'
    ;(bySubject[s] = bySubject[s] || []).push(t)
  }
  return [...SUBJECTS, '未设学科']
    .filter((s) => bySubject[s])
    .map((s) => ({
      subject: s,
      teachers: bySubject[s].sort((a, b) => gradeRank(a) - gradeRank(b) || a.employee_no.localeCompare(b.employee_no))
    }))
})

function openCreate() {
  editing.value = null
  form.value = { employee_no: '', name: '', phone: '', role: 'teacher', subject: '', password: '', classes: [] }
  showDialog.value = true
}

function openEdit(t) {
  editing.value = t
  form.value = { employee_no: t.employee_no, name: t.name, phone: t.phone || '', role: t.role, subject: t.subject || '', password: '', classes: [...(t.classes || [])] }
  showDialog.value = true
}

async function save() {
  try {
    const body = { ...form.value, subject: form.value.subject || null }
    delete body.classes
    if (!body.password) delete body.password
    let id
    if (editing.value) {
      await api.patch(`/teachers/${editing.value.id}`, body)
      id = editing.value.id
    } else {
      const { data } = await api.post('/teachers', body)
      id = data.id
    }
    await api.put(`/teachers/${id}/classes`, { class_names: form.value.classes })
    showToast('已保存')
    showDialog.value = false
    load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(t) {
  try {
    await showConfirmDialog({ title: '停用教师', message: `确定停用 ${t.name}？停用后无法登录。` })
    await api.delete(`/teachers/${t.id}`)
    showToast('已停用')
    load()
  } catch {
    /* 取消或拦截器提示 */
  }
}

function onSubjectConfirm({ selectedValues }) {
  form.value.subject = selectedValues[0]
  showSubjectPicker.value = false
}

onMounted(() => {
  load()
  loadClasses()
})
</script>

<template>
  <div>
    <van-search v-model="q" placeholder="搜索姓名 / 工号 / 学科" />
    <div class="toolbar">
      <van-button size="small" type="warning" icon="plus" @click="openCreate">新增教师</van-button>
      <span class="muted">按学科分组 · 组内按年级（初一→初三）排序</span>
    </div>

    <div v-for="g in grouped" :key="g.subject" class="subject-section">
      <div class="subject-header">{{ g.subject }} <span class="muted">{{ g.teachers.length }} 人</span></div>
      <div class="student-grid-admin">
        <div v-for="t in g.teachers" :key="t.id" class="student-tile" :class="{ inactive: !t.is_active }">
          <div class="st-head">
            <span class="st-name">{{ t.name }}</span>
            <van-tag v-if="t.role === 'admin'" type="primary" plain size="medium">管理员</van-tag>
            <van-tag v-if="!t.is_active" type="danger" plain size="medium">已停用</van-tag>
          </div>
          <div class="st-no">{{ t.employee_no }}</div>
          <div class="st-groups">
            <span class="st-group grade">{{ gradeLabel(t) }}</span>
            <span v-for="c in t.classes" :key="c" class="st-group">{{ c }}</span>
          </div>
          <div class="st-actions">
            <van-button size="mini" plain type="primary" icon="edit" @click="openEdit(t)">编辑</van-button>
            <van-button v-if="t.is_active" size="mini" plain type="danger" icon="delete-o" @click="remove(t)">停用</van-button>
          </div>
        </div>
      </div>
    </div>
    <van-empty v-if="!grouped.length" description="没有匹配的教师" />

    <van-dialog v-model:show="showDialog" :title="editing ? '编辑教师' : '新增教师'" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.employee_no" label="工号" placeholder="必填，登录账号" :disabled="!!editing" />
      <van-field v-model="form.name" label="姓名" placeholder="必填" />
      <van-field v-model="form.subject" label="学科" placeholder="点击选择学科" is-link readonly @click="showSubjectPicker = true" />
      <van-field v-model="form.phone" label="手机号" placeholder="选填，也可用于登录" />
      <van-field label="角色">
        <template #input>
          <van-radio-group v-model="form.role" direction="horizontal">
            <van-radio name="teacher">教师</van-radio>
            <van-radio name="admin">管理员</van-radio>
          </van-radio-group>
        </template>
      </van-field>
      <van-field v-model="form.password" type="password" label="密码" :placeholder="editing ? '留空则不修改' : '留空默认 123456'" />
      <van-field label="任教班级">
        <template #input>
          <div class="class-picker-wrap">
            <div v-if="form.classes.length" class="selected-classes">
              <span v-for="c in form.classes" :key="c" class="member-chip">
                {{ c }}
                <button type="button" class="chip-x" :aria-label="`移除${c}`" @click="toggleClass(c)">×</button>
              </span>
            </div>
            <div class="class-picker-inline">
              <div v-for="g in classOptions" :key="g.grade" class="class-picker-grade">
                <span class="grade-label">{{ g.grade }}</span>
                <button
                  v-for="c in g.classes"
                  :key="c"
                  type="button"
                  class="class-toggle"
                  :class="{ on: form.classes.includes(c) }"
                  @click="toggleClass(c)"
                >
                  {{ c.replace(g.grade, '') }}
                </button>
              </div>
              <div v-if="!allClasses.length" class="muted">暂无班级，请先导入学生数据</div>
            </div>
            <div class="muted" style="margin-top: 4px">点击班级编号选中/取消，× 移除已选</div>
          </div>
        </template>
      </van-field>
    </van-dialog>

    <van-popup v-model:show="showSubjectPicker" position="bottom" round>
      <van-picker :columns="subjectColumns" @confirm="onSubjectConfirm" @cancel="showSubjectPicker = false" />
    </van-popup>
  </div>
</template>
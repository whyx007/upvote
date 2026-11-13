<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'
import { SUBJECTS, GRADE_ORDER, gradeOfClass } from '../../constants'

const teachers = ref([])
const q = ref('')
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ employee_no: '', name: '', phone: '', role: 'teacher', subject: '', password: '' })
const showSubjectPicker = ref(false)
const subjectColumns = SUBJECTS.map((s) => ({ text: s, value: s }))

async function load() {
  const { data } = await api.get('/teachers', { params: { page_size: 500 } })
  teachers.value = data.items
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
  form.value = { employee_no: '', name: '', phone: '', role: 'teacher', subject: '', password: '' }
  showDialog.value = true
}

function openEdit(t) {
  editing.value = t
  form.value = { employee_no: t.employee_no, name: t.name, phone: t.phone || '', role: t.role, subject: t.subject || '', password: '' }
  showDialog.value = true
}

async function save() {
  try {
    const body = { ...form.value, subject: form.value.subject || null }
    if (!body.password) delete body.password
    if (editing.value) {
      await api.patch(`/teachers/${editing.value.id}`, body)
    } else {
      await api.post('/teachers', body)
    }
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

onMounted(load)
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
      <div class="roster-list">
        <div v-for="t in g.teachers" :key="t.id" class="roster-row">
          <div class="roster-info">
            <div class="roster-name">
              {{ t.name }} <span class="roster-no">{{ t.employee_no }}</span>
              <van-tag v-if="t.role === 'admin'" type="primary" plain size="medium">管理员</van-tag>
              <van-tag v-if="!t.is_active" type="danger" plain size="medium">已停用</van-tag>
            </div>
            <div class="roster-tags">
              <van-tag type="primary" plain size="medium">{{ gradeLabel(t) }}</van-tag>
              <van-tag v-for="c in t.classes" :key="c" plain size="medium">{{ c }}</van-tag>
            </div>
          </div>
          <div class="roster-actions">
            <van-button size="mini" plain type="primary" icon="edit" @click="openEdit(t)" />
            <van-button v-if="t.is_active" size="mini" plain type="danger" icon="delete-o" @click="remove(t)" />
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
    </van-dialog>

    <van-popup v-model:show="showSubjectPicker" position="bottom" round>
      <van-picker :columns="subjectColumns" @confirm="onSubjectConfirm" @cancel="showSubjectPicker = false" />
    </van-popup>
  </div>
</template>
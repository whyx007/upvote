<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'

const q = ref('')
const classFilter = ref('')
const classes = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ student_no: '', name: '', grade: '', class_name: '', enrollment_year: null })
const showClassPicker = ref(false)
const classColumns = computed(() => classes.value.map((c) => ({ text: c, value: c })))

async function load() {
  const { data } = await api.get('/students', {
    params: { q: q.value, class_name: classFilter.value, page: page.value, page_size: pageSize }
  })
  items.value = data.items
  total.value = data.total
}

async function loadClasses() {
  const { data } = await api.get('/classes')
  classes.value = data
}

function openCreate() {
  editing.value = null
  form.value = { student_no: '', name: '', grade: '', class_name: classFilter.value || '', enrollment_year: null }
  showDialog.value = true
}

function openEdit(s) {
  editing.value = s
  form.value = { student_no: s.student_no, name: s.name, grade: s.grade || '', class_name: s.class_name, enrollment_year: s.enrollment_year }
  showDialog.value = true
}

async function save() {
  try {
    if (editing.value) {
      await api.patch(`/students/${editing.value.id}`, form.value)
    } else {
      await api.post('/students', form.value)
    }
    showToast('已保存')
    showDialog.value = false
    load()
    loadClasses()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(s) {
  try {
    await showConfirmDialog({ title: '删除学生', message: `确定删除 ${s.name}？（停用，重新导入可恢复）` })
    await api.delete(`/students/${s.id}`)
    showToast('已删除')
    load()
  } catch {
    /* 取消或拦截器提示 */
  }
}

function onFilterConfirm({ selectedValues }) {
  classFilter.value = selectedValues[0] || ''
  showClassPicker.value = false
  page.value = 1
  load()
}

onMounted(() => {
  loadClasses()
  load()
})
</script>

<template>
  <div>
    <van-search v-model="q" placeholder="搜索姓名 / 学号" @search="page = 1; load()" @clear="page = 1; load()" />
    <van-cell title="班级筛选" :value="classFilter || '全部'" is-link @click="showClassPicker = true" />
    <div style="padding: 8px 16px">
      <van-button size="small" type="warning" icon="plus" @click="openCreate">新增学生</van-button>
      <span style="float: right; color: #969799; font-size: 13px; line-height: 32px">共 {{ total }} 人</span>
    </div>
    <van-cell-group inset>
      <van-cell v-for="s in items" :key="s.id" :title="`${s.name}（${s.student_no}）`" :label="`${s.grade || ''} ${s.class_name}`">
        <template #right>
          <van-button size="mini" plain type="primary" @click="openEdit(s)">编辑</van-button>
          <van-button size="mini" plain type="danger" style="margin-left: 6px" @click="remove(s)">删除</van-button>
        </template>
      </van-cell>
    </van-cell-group>
    <van-pagination v-model="page" :total-items="total" :items-per-page="pageSize" mode="simple" style="margin: 12px 16px" @change="load" />

    <van-dialog v-model:show="showDialog" :title="editing ? '编辑学生' : '新增学生'" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.student_no" label="学号" placeholder="必填，唯一" :disabled="!!editing" />
      <van-field v-model="form.name" label="姓名" placeholder="必填" />
      <van-field v-model="form.grade" label="年级" placeholder="如：初一" />
      <van-field v-model="form.class_name" label="班级" placeholder="如：初一1班（必填）" />
      <van-field v-model.number="form.enrollment_year" label="入学年份" type="digit" placeholder="如：2026" />
    </van-dialog>

    <van-popup v-model:show="showClassPicker" position="bottom" round>
      <van-picker :columns="[{ text: '全部', value: '' }, ...classColumns]" @confirm="onFilterConfirm" @cancel="showClassPicker = false" />
    </van-popup>
  </div>
</template>
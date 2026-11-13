<script setup>
import { onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'

const q = ref('')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ employee_no: '', name: '', phone: '', role: 'teacher', password: '' })

async function load() {
  const { data } = await api.get('/teachers', { params: { q: q.value, page: page.value, page_size: pageSize } })
  items.value = data.items
  total.value = data.total
}

function openCreate() {
  editing.value = null
  form.value = { employee_no: '', name: '', phone: '', role: 'teacher', password: '' }
  showDialog.value = true
}

function openEdit(t) {
  editing.value = t
  form.value = { employee_no: t.employee_no, name: t.name, phone: t.phone || '', role: t.role, password: '' }
  showDialog.value = true
}

async function save() {
  try {
    const body = { ...form.value }
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

onMounted(load)
</script>

<template>
  <div>
    <van-search v-model="q" placeholder="搜索姓名 / 工号" @search="page = 1; load()" @clear="page = 1; load()" />
    <div style="padding: 8px 16px">
      <van-button size="small" type="warning" icon="plus" @click="openCreate">新增教师</van-button>
      <span style="float: right; color: #969799; font-size: 13px; line-height: 32px">共 {{ total }} 人</span>
    </div>
    <van-cell-group inset>
      <van-cell v-for="t in items" :key="t.id" :title="`${t.name}（${t.employee_no}）`" :label="`${t.role === 'admin' ? '管理员' : '教师'}${t.is_active ? '' : ' · 已停用'}${t.phone ? ' · ' + t.phone : ''}`">
        <template #right>
          <van-button size="mini" plain type="primary" @click="openEdit(t)">编辑</van-button>
          <van-button v-if="t.is_active" size="mini" plain type="danger" style="margin-left: 6px" @click="remove(t)">停用</van-button>
        </template>
      </van-cell>
    </van-cell-group>
    <van-pagination v-model="page" :total-items="total" :items-per-page="pageSize" mode="simple" style="margin: 12px 16px" @change="load" />

    <van-dialog v-model:show="showDialog" :title="editing ? '编辑教师' : '新增教师'" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.employee_no" label="工号" placeholder="必填，登录账号" :disabled="!!editing" />
      <van-field v-model="form.name" label="姓名" placeholder="必填" />
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
  </div>
</template>
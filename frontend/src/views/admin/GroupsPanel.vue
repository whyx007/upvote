<script setup>
import { onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'

const items = ref([])
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ name: '', class_name: '', members: '' })

async function load() {
  const { data } = await api.get('/groups')
  items.value = data.items
}

function openCreate() {
  editing.value = null
  form.value = { name: '', class_name: '', members: '' }
  showDialog.value = true
}

function openEdit(g) {
  editing.value = g
  form.value = { name: g.name, class_name: g.class_name, members: '' }
  showToast('成员学号留空表示不修改成员')
  showDialog.value = true
}

async function save() {
  try {
    const body = { name: form.value.name, class_name: form.value.class_name }
    if (form.value.members.trim() || !editing.value) {
      body.member_student_nos = form.value.members.split(/[,，、;；\s]+/).filter(Boolean)
    }
    if (editing.value) {
      await api.patch(`/groups/${editing.value.id}`, body)
    } else {
      await api.post('/groups', body)
    }
    showToast('已保存')
    showDialog.value = false
    load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(g) {
  try {
    await showConfirmDialog({ title: '删除小组', message: `确定删除「${g.name}」？历史点赞记录保留。` })
    await api.delete(`/groups/${g.id}`)
    showToast('已删除')
    load()
  } catch {
    /* 取消或拦截器提示 */
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div style="padding: 12px 16px">
      <van-button size="small" type="warning" icon="plus" @click="openCreate">新增小组</van-button>
    </div>
    <van-cell-group inset>
      <van-cell v-for="g in items" :key="g.id" :title="`${g.name}（${g.member_count} 人）`" :label="g.class_name">
        <template #right>
          <van-button size="mini" plain type="primary" @click="openEdit(g)">编辑</van-button>
          <van-button size="mini" plain type="danger" style="margin-left: 6px" @click="remove(g)">删除</van-button>
        </template>
      </van-cell>
    </van-cell-group>
    <van-empty v-if="!items.length" description="还没有学习小组" />

    <van-dialog v-model:show="showDialog" :title="editing ? '编辑小组' : '新增小组'" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.name" label="小组名称" placeholder="如：星辰组" />
      <van-field v-model="form.class_name" label="班级" placeholder="如：初一1班" />
      <van-field v-model="form.members" label="成员学号" type="textarea" rows="3" autosize placeholder="逗号分隔，如：2026001,2026002" />
    </van-dialog>
  </div>
</template>
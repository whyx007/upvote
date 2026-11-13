<script setup>
import { onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../../api'

const items = ref([])
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ name: '', cost_coins: 10, stock: null })

async function load() {
  const { data } = await api.get('/rewards')
  items.value = data.items
}

function openCreate() {
  editing.value = null
  form.value = { name: '', cost_coins: 10, stock: null }
  showDialog.value = true
}

function openEdit(r) {
  editing.value = r
  form.value = { name: r.name, cost_coins: r.cost_coins, stock: r.stock }
  showDialog.value = true
}

async function save() {
  try {
    const body = { name: form.value.name, cost_coins: Number(form.value.cost_coins), stock: form.value.stock === '' || form.value.stock === null ? null : Number(form.value.stock) }
    if (editing.value) {
      await api.patch(`/rewards/${editing.value.id}`, body)
    } else {
      await api.post('/rewards', body)
    }
    showToast('已保存')
    showDialog.value = false
    load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function remove(r) {
  try {
    await showConfirmDialog({ title: '下架奖励', message: `确定下架「${r.name}」？` })
    await api.delete(`/rewards/${r.id}`)
    showToast('已下架')
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
      <van-button size="small" type="warning" icon="plus" @click="openCreate">新增奖励</van-button>
    </div>
    <van-cell-group inset>
      <van-cell v-for="r in items" :key="r.id" :title="r.name" :label="`库存：${r.stock === null ? '不限量' : r.stock}`" :value="`⭐ ${r.cost_coins}`">
        <template #right>
          <van-button size="mini" plain type="primary" style="margin-left: 8px" @click="openEdit(r)">编辑</van-button>
          <van-button size="mini" plain type="danger" style="margin-left: 6px" @click="remove(r)">下架</van-button>
        </template>
      </van-cell>
    </van-cell-group>
    <van-empty v-if="!items.length" description="还没有奖励，先添加兑换目录" />

    <van-dialog v-model:show="showDialog" :title="editing ? '编辑奖励' : '新增奖励'" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.name" label="名称" placeholder="如：笔记本" />
      <van-field v-model.number="form.cost_coins" label="所需星灿币" type="digit" placeholder="如：10" />
      <van-field v-model="form.stock" label="库存" type="digit" placeholder="留空 = 不限量" />
    </van-dialog>
  </div>
</template>
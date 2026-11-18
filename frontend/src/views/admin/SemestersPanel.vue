<script setup>
import { onMounted, ref } from 'vue'
import { showToast } from 'vant'
import api from '../../api'

const items = ref([])
const showDialog = ref(false)
const form = ref({ name: '', start_date: '', end_date: '' })

async function load() {
  const { data } = await api.get('/semesters')
  items.value = data.items
}

async function activate(s) {
  try {
    await api.post(`/semesters/${s.id}/activate`)
    showToast(`已激活：${s.name}`)
    load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function save() {
  try {
    await api.post('/semesters', form.value)
    showToast('已创建')
    showDialog.value = false
    form.value = { name: '', start_date: '', end_date: '' }
    load()
  } catch {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <div>
    <van-notice-bar left-icon="info-o" wrapable text="点赞与兑换都计入当前激活学期；切换学期后，学期余额重新累计，就读期间总累计保留。" />
    <div style="padding: 12px 16px">
      <van-button size="small" type="warning" icon="plus" @click="showDialog = true">新增学期</van-button>
    </div>
    <van-cell-group inset>
      <van-cell v-for="s in items" :key="s.id" :title="s.name" :label="`${s.start_date} ~ ${s.end_date}`">
        <template #value>
          <van-tag v-if="s.is_current" type="warning" size="medium">当前学期</van-tag>
          <van-button v-else size="mini" plain type="warning" @click="activate(s)">激活</van-button>
        </template>
      </van-cell>
    </van-cell-group>
    <van-empty v-if="!items.length" description="请先创建并激活一个学期" />

    <van-dialog teleport="body" v-model:show="showDialog" title="新增学期" show-cancel-button class="form-dialog" @confirm="save">
      <van-field v-model="form.name" label="名称" placeholder="如：2026-2027学年第一学期" />
      <van-field v-model="form.start_date" label="开始日期" type="date" />
      <van-field v-model="form.end_date" label="结束日期" type="date" />
    </van-dialog>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  show: Boolean,
  title: { type: String, default: '选择成员' },
  students: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:show', 'confirm'])

const q = ref('')
const checked = ref([])

watch(
  () => props.show,
  (v) => {
    if (v) {
      checked.value = [...props.selected]
      q.value = ''
    }
  }
)

const filtered = computed(() =>
  props.students.filter((s) => !q.value || s.name.includes(q.value) || s.student_no.includes(q.value))
)
const allChecked = computed(() => filtered.value.length > 0 && filtered.value.every((s) => checked.value.includes(s.id)))

function toggle(id) {
  const i = checked.value.indexOf(id)
  if (i >= 0) checked.value.splice(i, 1)
  else checked.value.push(id)
}

function toggleAll() {
  if (allChecked.value) {
    checked.value = checked.value.filter((id) => !filtered.value.some((s) => s.id === id))
  } else {
    checked.value = [...new Set([...checked.value, ...filtered.value.map((s) => s.id)])]
  }
}

function confirm() {
  emit('confirm', [...checked.value])
}
</script>

<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    :style="{ height: '82%' }"
    @update:show="(v) => emit('update:show', v)"
  >
    <div class="picker-head">
      <b>{{ title }}</b>
      <van-button size="small" type="warning" round @click="confirm">确定（{{ checked.length }} 人）</van-button>
    </div>
    <van-search v-model="q" placeholder="搜索姓名 / 学号" />
    <div class="picker-tools">
      <van-checkbox :model-value="allChecked" shape="square" @update:model-value="toggleAll">全选</van-checkbox>
      <van-button size="mini" plain @click="checked = []">清空</van-button>
      <span class="muted">一人可同时在多个小组</span>
    </div>
    <div class="picker-list">
      <van-checkbox-group v-model="checked">
        <van-cell v-for="s in filtered" :key="s.id" clickable @click="toggle(s.id)">
          <template #title>
            <span class="roster-name">{{ s.name }}</span>
            <span class="roster-no">{{ s.student_no }}</span>
            <van-tag v-for="gname in s.groups" :key="gname" plain type="warning" size="medium" style="margin-left: 4px">{{ gname }}</van-tag>
          </template>
          <template #right>
            <van-checkbox :name="s.id" shape="square" @click.stop />
          </template>
        </van-cell>
      </van-checkbox-group>
      <van-empty v-if="!filtered.length" description="没有匹配的学生" />
    </div>
  </van-popup>
</template>
<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  show: Boolean,
  title: { type: String, default: '选择成员' },
  students: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] },
  excludeIds: { type: Array, default: () => [] }
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

// 只排除已在本组的学生；已在其他组的学生仍可选，确认时提醒
const filtered = computed(() =>
  props.students.filter(
    (s) => !props.excludeIds.includes(s.id) && (!q.value || s.name.includes(q.value) || s.student_no.includes(q.value))
  )
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
    teleport="body"
    :show="show"
    position="bottom"
    round
    :style="{ height: '82%' }"
    @update:show="(v) => emit('update:show', v)"
  >
    <div class="picker-head">
      <b>{{ title }}</b>
      <van-button size="small" type="warning" round @click="confirm">确定添加（{{ checked.length }} 人）</van-button>
    </div>
    <van-search v-model="q" placeholder="搜索姓名 / 学号" />
    <div class="picker-tools">
      <van-checkbox :model-value="allChecked" shape="square" @update:model-value="toggleAll">全选</van-checkbox>
      <van-button size="mini" plain @click="checked = []">清空</van-button>
      <span class="muted">已在本组的学生不显示；已在其他组仍可选，确认时会提醒</span>
    </div>
    <div class="picker-list">
      <div class="picker-grid">
        <div
          v-for="s in filtered"
          :key="s.id"
          role="button"
          tabindex="0"
          class="picker-tile"
          :class="{ checked: checked.includes(s.id) }"
          :title="`${s.name} ${s.student_no}${s.groups?.length ? `（已在：${s.groups.join('、')}）` : ''}`"
          @click="toggle(s.id)"
          @keydown.enter.prevent="toggle(s.id)"
          @keydown.space.prevent="toggle(s.id)"
        >
          <van-checkbox
            :model-value="checked.includes(s.id)"
            shape="square"
            @click.stop
            @update:model-value="toggle(s.id)"
          />
          <span class="picker-tile-name">{{ s.name }}</span>
          <span v-if="s.groups?.length" class="picker-tile-other">已在其他组</span>
        </div>
      </div>
      <van-empty v-if="!filtered.length" description="没有可添加的学生（可能都已在本组）" />
    </div>
  </van-popup>
</template>
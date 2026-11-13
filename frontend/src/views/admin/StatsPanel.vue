<script setup>
import { onMounted, ref } from 'vue'
import api, { downloadBlob } from '../../api'

const overview = ref(null)

async function load() {
  const { data } = await api.get('/stats/overview')
  overview.value = data
}

onMounted(load)
</script>

<template>
  <div>
    <van-loading v-if="!overview" style="text-align: center; padding: 24px" />
    <template v-else>
      <van-cell title="统计学期" :value="overview.semester ? overview.semester.name : '未激活学期'" />
      <div class="stat-grid">
        <div class="stat-card"><div class="num">{{ overview.total_students }}</div><div class="label">学生数</div></div>
        <div class="stat-card"><div class="num">{{ overview.total_teachers }}</div><div class="label">教师数</div></div>
        <div class="stat-card"><div class="num">{{ overview.total_likes }}</div><div class="label">本学期点赞</div></div>
        <div class="stat-card"><div class="num">{{ overview.total_coins_issued }}</div><div class="label">发放星灿币</div></div>
        <div class="stat-card"><div class="num">{{ overview.total_redemptions }}</div><div class="label">兑换次数</div></div>
        <div class="stat-card"><div class="num">{{ overview.total_coins_redeemed }}</div><div class="label">消耗星灿币</div></div>
      </div>
      <div style="padding: 0 16px 12px">
        <van-button type="primary" plain block icon="down" @click="downloadBlob('/stats/export', 'upvote_stats.xlsx')">导出全校星灿币统计表（Excel）</van-button>
      </div>
      <div class="section-title">星灿币排行 TOP 10</div>
      <van-cell-group inset>
        <van-cell v-for="(s, i) in overview.top_students" :key="s.student_no" :title="`${i + 1}. ${s.name}`" :label="s.class_name" :value="`⭐ ${s.semester_balance}（累计 ${s.total_balance}）`" />
      </van-cell-group>
      <div class="section-title">班级概览</div>
      <van-cell-group inset style="margin-bottom: 16px">
        <van-cell v-for="c in overview.per_class" :key="c.class_name" :title="c.class_name" :label="`${c.student_count} 人`" :value="`👍 ${c.likes}`" />
      </van-cell-group>
    </template>
  </div>
</template>
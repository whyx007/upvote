<script setup>
import { ref } from 'vue'
import UserMenu from '../components/UserMenu.vue'
import ClassWorkspace from './admin/ClassWorkspace.vue'
import StudentRosterPanel from './admin/StudentRosterPanel.vue'
import TeachersPanel from './admin/TeachersPanel.vue'
import ImportPanel from './admin/ImportPanel.vue'
import SemestersPanel from './admin/SemestersPanel.vue'
import RewardsPanel from './admin/RewardsPanel.vue'
import RedeemPanel from './admin/RedeemPanel.vue'
import StatsPanel from './admin/StatsPanel.vue'
import UsagePanel from './admin/UsagePanel.vue'

const tab = ref('class')
</script>

<template>
  <div class="page">
    <van-nav-bar title="星灿管理台" fixed placeholder>
      <template #right><UserMenu /></template>
    </van-nav-bar>
    <van-tabs v-model:active="tab" scrollable sticky>
      <van-tab title="班级" name="class"><ClassWorkspace v-if="tab === 'class'" /></van-tab>
      <van-tab title="名册" name="roster"><StudentRosterPanel v-if="tab === 'roster'" /></van-tab>
      <van-tab title="教师" name="teachers"><TeachersPanel v-if="tab === 'teachers'" /></van-tab>
      <van-tab title="名单导入" name="import"><ImportPanel v-if="tab === 'import'" /></van-tab>
      <van-tab title="学期" name="semesters"><SemestersPanel v-if="tab === 'semesters'" /></van-tab>
      <van-tab title="奖励" name="rewards"><RewardsPanel v-if="tab === 'rewards'" /></van-tab>
      <van-tab title="兑换" name="redeem"><RedeemPanel v-if="tab === 'redeem'" /></van-tab>
      <van-tab title="统计" name="stats"><StatsPanel v-if="tab === 'stats'" /></van-tab>
      <van-tab title="使用统计" name="usage"><UsagePanel v-if="tab === 'usage'" mode="admin" /></van-tab>
    </van-tabs>
  </div>
</template>
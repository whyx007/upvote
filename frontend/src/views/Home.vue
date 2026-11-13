<script setup>
import { useAuthStore } from '../stores/auth'
import TeacherHome from './TeacherHome.vue'
import AdminHome from './AdminHome.vue'

const auth = useAuthStore()
</script>

<template>
  <AdminHome v-if="auth.isAdmin" />
  <TeacherHome v-else />
</template>
<script setup>
import { useRegisterSW } from 'virtual:pwa-register/vue'

// PWA 新版本检测：发现更新时显示横幅，点击一键切换；每 30 分钟主动检查一次
const { needRefresh, updateServiceWorker } = useRegisterSW({
  onRegisteredSW(_swUrl, registration) {
    if (registration) {
      setInterval(() => registration.update().catch(() => {}), 30 * 60 * 1000)
    }
  }
})
</script>

<template>
  <router-view />
  <transition name="van-fade">
    <div v-if="needRefresh" class="update-banner" @click="updateServiceWorker(true)">
      <span class="update-dot"></span>
      发现新版本 · 点击立即更新
    </div>
  </transition>
</template>
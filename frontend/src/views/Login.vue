<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function onSubmit() {
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', { username: username.value, password: password.value })
    auth.setLogin(data.token, data.teacher)
    showToast(`欢迎，${data.teacher.name}`)
    router.push('/')
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page" style="display: flex; flex-direction: column; justify-content: center; padding: 24px">
    <div style="text-align: center; margin-bottom: 32px">
      <img src="/icons/icon-192.png" alt="星灿" style="width: 88px; height: 88px; border-radius: 20px" />
      <h2 style="margin: 12px 0 4px">星灿点赞积分系统</h2>
      <p style="color: #969799; margin: 0">十一初 · 私域部署</p>
    </div>
    <van-form @submit="onSubmit">
      <van-cell-group inset>
        <van-field v-model="username" name="username" label="工号/手机" placeholder="请输入工号或手机号" :rules="[{ required: true, message: '请输入工号或手机号' }]" />
        <van-field v-model="password" type="password" name="password" label="密码" placeholder="请输入密码" :rules="[{ required: true, message: '请输入密码' }]" />
      </van-cell-group>
      <div style="margin: 24px 16px">
        <van-button round block type="warning" native-type="submit" :loading="loading">登 录</van-button>
      </div>
    </van-form>
  </div>
</template>
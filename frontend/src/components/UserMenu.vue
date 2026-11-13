<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showConfirmDialog } from 'vant'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const showMenu = ref(false)
const showPassword = ref(false)
const oldPassword = ref('')
const newPassword = ref('')

async function changePassword() {
  try {
    await api.post('/auth/change-password', { old_password: oldPassword.value, new_password: newPassword.value })
    showToast('密码已修改')
    showPassword.value = false
    oldPassword.value = ''
    newPassword.value = ''
  } catch {
    /* 拦截器已提示 */
  }
}

async function logout() {
  await showConfirmDialog({ title: '退出登录', message: '确定退出当前账号吗？' })
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <van-icon name="manager-o" size="22" @click="showMenu = true" />
  <van-popup v-model:show="showMenu" position="bottom" round :style="{ paddingBottom: '16px' }">
    <van-cell-group :title="`${auth.teacher?.name}（${auth.teacher?.employee_no}）`">
      <van-cell title="修改密码" is-link icon="lock" @click="showMenu = false; showPassword = true" />
      <van-cell title="退出登录" is-link icon="revoke" @click="showMenu = false; logout()" />
    </van-cell-group>
  </van-popup>
  <van-dialog v-model:show="showPassword" title="修改密码" show-cancel-button class="form-dialog" @confirm="changePassword">
    <van-field v-model="oldPassword" type="password" label="原密码" placeholder="请输入原密码" />
    <van-field v-model="newPassword" type="password" label="新密码" placeholder="至少 6 位" />
  </van-dialog>
</template>
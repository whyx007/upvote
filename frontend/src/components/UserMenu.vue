<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showConfirmDialog } from 'vant'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { roleLabel as labelOfRole } from '../constants'

const props = defineProps({
  roleKey: { type: String, default: '' }
})

const auth = useAuthStore()
const router = useRouter()
const showMenu = ref(false)
const showPassword = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const version = __APP_VERSION__

const role = computed(() => {
  const key = props.roleKey || (auth.isAdmin ? 'admin' : auth.isSubjectLead ? 'subject_lead' : 'teacher')
  return { key, label: labelOfRole(key) }
})
const initial = computed(() => (auth.teacher?.name || '?').slice(-2))
const accountTitle = computed(
  () => `${auth.teacher?.name || ''}（${auth.teacher?.employee_no || ''}） · ${role.value.label}`
)

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
  <div class="nav-user" role="button" :aria-label="accountTitle" @click="showMenu = true">
    <span class="nav-user-avatar" :class="`role-${role.key}`">{{ initial }}</span>
    <span class="nav-user-text">
      <span class="nav-user-name">{{ auth.teacher?.name }}</span>
      <span class="nav-user-role" :class="`role-${role.key}`">{{ role.label }}</span>
    </span>
    <van-icon name="arrow-down" class="nav-user-caret" />
  </div>

  <van-popup teleport="body" v-model:show="showMenu" position="bottom" round :style="{ paddingBottom: '16px' }">
    <van-cell-group :title="accountTitle">
      <van-cell title="修改密码" is-link icon="lock" @click="showMenu = false; showPassword = true" />
      <van-cell title="退出登录" is-link icon="revoke" @click="showMenu = false; logout()" />
      <van-cell title="版本（构建时间）" :value="version" />
    </van-cell-group>
  </van-popup>

  <van-dialog teleport="body" v-model:show="showPassword" title="修改密码" show-cancel-button class="form-dialog" @confirm="changePassword">
    <van-field v-model="oldPassword" type="password" label="原密码" placeholder="请输入原密码" />
    <van-field v-model="newPassword" type="password" label="新密码" placeholder="至少 6 位" />
  </van-dialog>
</template>
import axios from 'axios'
import { showToast } from 'vant'
import { useAuthStore } from './stores/auth'
import router from './router'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) cfg.headers.Authorization = `Bearer ${auth.token}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) {
      const auth = useAuthStore()
      auth.logout()
      router.push('/login')
      showToast('请重新登录')
    } else {
      showToast(typeof detail === 'string' ? detail : '操作失败，请重试')
    }
    return Promise.reject(err)
  }
)

export async function downloadBlob(url, filename, params) {
  const r = await api.get(url, { responseType: 'blob', params })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export default api
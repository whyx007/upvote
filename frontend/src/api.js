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
    const url = err.config?.url || ''
    const isLoginRequest = url.includes('/auth/login')

    // 登录失败：提示真实原因（工号或密码错误），不要误报“请重新登录”
    if (isLoginRequest) {
      showToast(typeof detail === 'string' ? detail : '工号或密码错误')
      return Promise.reject(err)
    }

    if (status === 401) {
      const auth = useAuthStore()
      if (auth.token) {
        auth.logout()
        router.push('/login')
        showToast('登录已过期，请重新登录')
      } else {
        showToast(typeof detail === 'string' ? detail : '请先登录')
      }
    } else if (status === 403) {
      showToast(typeof detail === 'string' ? detail : '没有操作权限')
    } else {
      showToast(typeof detail === 'string' ? detail : '操作失败，请重试')
    }
    return Promise.reject(err)
  }
)

export async function downloadBlob(url, filename, params, options = {}) {
  const r = await api.get(url, { responseType: 'blob', params, ...options })

  // 安卓 APK：WebView 内 <a download> 不会触发下载，交给原生桥写入「下载」目录
  const bridge = typeof window !== 'undefined' ? window.UpvoteNative : null
  if (bridge && typeof bridge.saveBlob === 'function') {
    const mime = r.headers?.['content-type'] || r.data?.type || 'application/octet-stream'
    try {
      await bridge.saveBlob(filename, r.data, mime)
      showToast('已保存到「下载」目录')
      return
    } catch {
      /* 桥接不可用时回退到浏览器下载 */
    }
  }

  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export default api
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

// 构建版本号（北京时间），用于界面展示与缓存排查
const buildVersion = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 16).replace('T', ' ')

// 安卓 APK 构建：资源已打包进 APK，由本地回环服务提供，不需要 Service Worker
// （SW 会缓存 index.html，APK 升级后容易读到旧壳）
const isApkBuild = process.env.UPVOTE_APK === '1'

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(buildVersion)
  },
  plugins: [
    vue(),
    VitePWA({
      disable: isApkBuild,
      registerType: 'autoUpdate',
      manifest: {
        name: '星灿点赞积分系统',
        short_name: '星灿点赞',
        description: '十一初点赞积分系统（星灿币）',
        theme_color: '#ff9f43',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,svg,woff2}'],
        navigateFallback: '/index.html',
        runtimeCaching: [{ urlPattern: /\/api\/.*/, handler: 'NetworkOnly' }]
      }
    })
  ],
  server: {
    host: '0.0.0.0',
    proxy: { '/api': 'http://127.0.0.1:8000' }
  }
})
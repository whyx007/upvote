import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
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
import { defineConfig, loadEnv } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [uni()],
    server: {
      port: 9000,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: env.KAI_H5_API_TARGET || env.WOD_H5_API_TARGET || 'https://wod.kai.com',
          changeOrigin: true,
        },
      },
    },
  }
})

import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/theme.css'
import { finishAppLaunch } from './utils/app-launch'
import { hasCurrentPrivacyConsent } from './utils/privacy-consent'

export function createApp() {
  const app = createSSRApp(App)
  app.use(createPinia())
  app.mixin({
    onReady() {
      const pages = getCurrentPages()
      const route = pages[pages.length - 1]?.route
      // The accepted consent page is only a router. Login owns its reveal so
      // its component entrance starts when the native cover actually closes.
      if (route === 'pages/login/index') return
      if (route === 'pages/privacy-consent/index' && hasCurrentPrivacyConsent()) return
      finishAppLaunch()
    },
  })
  return { app }
}

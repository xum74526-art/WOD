/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENABLE_DIRECT_TRADE?: string
  readonly VITE_RECHARGE_MIN_AMOUNT_CNY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}

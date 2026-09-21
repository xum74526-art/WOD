import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getToken, setToken, clearAuth } from '@/utils/auth'
import { useAssetStore } from './asset'
import * as userApi from '@/api/user'
import type { UserInfo } from '@/api/user'
import { signOutCurrentDevice } from '@/utils/session-logout'

export const useUserStore = defineStore('user', () => {
  const token = ref(getToken())
  const userInfo = ref<UserInfo | null>(null)
  const role = ref<'personal' | 'supplier'>('personal')
  // The first page must not render protected content until a persisted token
  // has been checked (or we have confirmed that there is no token). This
  // prevents the home tab flashing before an expired session redirects to
  // login.
  const authReady = ref(false)
  let restorePromise: Promise<boolean> | null = null

  function applySession(res: { token: string; user: UserInfo }) {
    // A successful login may follow an expired session or an OAuth callback.
    // Never let the next account inherit the previous account's cached assets.
    useAssetStore().reset()
    token.value = res.token
    setToken(res.token)
    userInfo.value = res.user
    role.value = (res.user.role as 'personal' | 'supplier') || 'personal'
    authReady.value = true
    uni.$emit('wod-session-changed')
    return res
  }

  async function login(phone: string, password: string) {
    const res = await userApi.login(phone, password)
    return applySession(res)
  }

  async function register(username: string, phone: string, password: string, invite_code?: string, captcha_key?: string, captcha_code?: string) {
    const res = await userApi.register(username, phone, password, invite_code, captcha_key, captcha_code)
    return applySession(res)
  }

  async function loginWithKaiTicket(ticket: string) {
    const res = await userApi.exchangeKaiTicket(ticket)
    return applySession(res)
  }

  async function bindKaiIdentity(ticket: string) {
    const res = await userApi.exchangeKaiBindTicket(ticket)
    userInfo.value = res.user
    role.value = (res.user.role as 'personal' | 'supplier') || 'personal'
    uni.$emit('wod-kai-binding-changed', res)
    return res
  }

  async function fetchProfile() {
    userInfo.value = await userApi.getProfile()
    role.value = (userInfo.value?.role as 'personal' | 'supplier') || 'personal'
    return userInfo.value
  }

  async function switchRole() {
    const res = await userApi.switchRole()
    role.value = res.role as 'personal' | 'supplier'
    if (userInfo.value) userInfo.value = { ...userInfo.value, role: role.value }
    // Role-specific asset/hosting views must never reuse the previous mode's
    // cached panels or records.
    useAssetStore().reset()
    uni.$emit('wod-session-changed')
    return role.value
  }

  function restore(): Promise<boolean> {
    if (authReady.value) return Promise.resolve(!!token.value)
    if (restorePromise) return restorePromise
    if (!token.value) {
      authReady.value = true
      return Promise.resolve(false)
    }
    restorePromise = fetchProfile()
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        authReady.value = true
        restorePromise = null
      })
    return restorePromise
  }

  function clearSession() {
    token.value = ''
    userInfo.value = null
    role.value = 'personal'
    authReady.value = true
    useAssetStore().reset()
  }

  function logout() {
    clearSession()
    clearAuth()
    uni.$emit('wod-auth-expired')
  }

  function signOut() {
    return signOutCurrentDevice(userApi.logoutCurrentSession, logout)
  }

  const isLogin = computed(() => !!token.value)
  const canSwitchRole = computed(() => userInfo.value?.supplier_status === 'approved')

  return { token, userInfo, role, isLogin, authReady, canSwitchRole, login, register, loginWithKaiTicket, bindKaiIdentity, fetchProfile, restore, switchRole, clearSession, logout, signOut }
})

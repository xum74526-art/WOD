<template>
  <view class="page">
    <AppNavBar :title="t('onlineService')" />

    <view class="service-banner">
      <view class="service-dot" :class="serviceMode"></view>
      <view class="service-copy">
        <text class="service-title">{{ serviceMode === 'ai_assisted' ? t('supportAiAssisted') : t('supportSelfService') }}</text>
      </view>
      <view v-if="tickets.length" class="ticket-count" @tap="refreshTickets">
        {{ t('supportTicketsCount', { count: tickets.length }) }}
      </view>
    </view>

    <scroll-view v-if="tickets.length" scroll-x class="tickets-strip" show-scrollbar="false">
      <view class="tickets-row">
        <view v-for="ticket in tickets" :key="ticket.id" class="ticket-card">
          <text class="ticket-no">{{ ticket.ticket_no }}</text>
          <text class="ticket-status">{{ ticketStatusLabel(ticket.status) }}</text>
          <text class="ticket-subject">{{ ticket.subject }}</text>
        </view>
      </view>
    </scroll-view>

    <view v-if="initialLoading" class="state-box">
      <view class="spinner"></view>
      <text>{{ t('supportLoadingHistory') }}</text>
    </view>
    <view v-else-if="loadError" class="state-box error-state">
      <text>{{ t('supportHistoryFailed') }}</text>
      <view class="retry-pill" @tap="loadSession">{{ t('retry') }}</view>
    </view>

    <scroll-view v-else scroll-y class="chat-body" :scroll-into-view="scrollToId">
      <view class="msg-row assistant">
        <view class="avatar service-avatar">{{ t('supportAvatar') }}</view>
        <view class="assistant-stack">
          <view class="bubble assistant-bubble">{{ t('supportWelcome') }}</view>
          <scroll-view v-if="!messages.length" scroll-x class="quick-scroll" show-scrollbar="false">
            <view class="quick-row">
              <view v-for="item in quickQuestions" :key="item.question" class="quick-pill" @tap="sendQuick(item.question)">
                {{ item.label }}
              </view>
            </view>
          </scroll-view>
        </view>
      </view>

      <view v-for="(message, index) in messages" :key="message.localId" :id="`msg-${message.localId}`" class="msg-row" :class="message.role">
        <template v-if="message.role === 'user'">
          <view class="user-stack">
            <view class="bubble user-bubble">{{ message.content }}</view>
            <view v-if="message.status === 'sending'" class="delivery-note">{{ t('supportSending') }}</view>
            <view v-else-if="message.status === 'failed'" class="delivery-note failed" @tap="retryMessage(message)">
              {{ t('supportSendFailedRetry') }}
            </view>
          </view>
          <view class="avatar user-avatar">{{ t('k_16815254') }}</view>
        </template>
        <template v-else>
          <view class="avatar service-avatar">{{ t('supportAvatar') }}</view>
          <view class="assistant-stack">
            <view class="bubble assistant-bubble">{{ message.content }}</view>
            <view v-if="message.can_create_ticket && !message.ticket" class="ticket-action" :class="{ disabled: creatingTicketId === message.localId }" @tap="createTicket(message, index)">
              {{ creatingTicketId === message.localId ? t('supportCreatingTicket') : t('supportCreateTicket') }}
            </view>
            <view v-if="message.ticket" class="created-ticket">
              <text class="created-ticket-title">{{ t('supportTicketCreated') }}</text>
              <text class="created-ticket-no">{{ message.ticket.ticket_no }}</text>
              <text class="created-ticket-status">{{ ticketStatusLabel(message.ticket.status) }}</text>
            </view>
          </view>
        </template>
      </view>

      <view v-if="sending" class="msg-row assistant">
        <view class="avatar service-avatar">{{ t('supportAvatar') }}</view>
        <view class="bubble assistant-bubble typing">
          <view class="typing-dot"></view><view class="typing-dot"></view><view class="typing-dot"></view>
        </view>
      </view>
      <view id="msg-bottom" class="scroll-anchor"></view>
    </scroll-view>

    <view class="privacy-tip">{{ t('supportPrivacyTip') }}</view>
    <view class="input-bar" :style="{ paddingBottom: 'calc(16rpx + var(--safe-bottom))' }">
      <input
        v-model="inputText"
        class="msg-input"
        :placeholder="t('supportInputPlaceholder')"
        placeholder-class="msg-ph"
        :maxlength="1000"
        :adjust-position="true"
        confirm-type="send"
        @confirm="onSend"
      />
      <view class="send-btn" :class="{ disabled: !inputText.trim() || sending || initialLoading }" @tap="onSend">
        {{ t('send') }}
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import AppNavBar from '@/components/AppNavBar.vue'
import {
  createSupportTicket,
  getSupportSession,
  listSupportTickets,
  sendMessage,
  type SupportMessage,
  type SupportMode,
  type SupportTicket,
  type SupportTicketStatus,
} from '@/api/chat'
import { useI18nStore } from '@/store/i18n'
import { supportApiLanguage } from '@/utils/language'

interface ViewMessage {
  localId: string
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  responseMode?: string
  topic?: string | null
  can_create_ticket?: boolean
  replyToId?: number | null
  status?: 'sending' | 'sent' | 'failed'
  clientMessageId?: string
  ticket?: SupportTicket
}

const i18n = useI18nStore()
const { t } = i18n
const inputText = ref('')
const sending = ref(false)
const initialLoading = ref(true)
const loadError = ref(false)
const scrollToId = ref('')
const conversationId = ref<number | null>(null)
const serviceMode = ref<SupportMode>('self_service')
const messages = ref<ViewMessage[]>([])
const tickets = ref<SupportTicket[]>([])
const creatingTicketId = ref('')

const quickQuestions = computed(() => [
  { label: t('supportQuickPurchase'), question: t('supportQuickPurchaseQuestion') },
  { label: t('supportQuickCompute'), question: t('supportQuickComputeQuestion') },
  { label: t('supportQuickHosting'), question: t('supportQuickHostingQuestion') },
  { label: t('supportQuickPayment'), question: t('supportQuickPaymentQuestion') },
  { label: t('supportQuickNotification'), question: t('supportQuickNotificationQuestion') },
])

function fromServer(message: SupportMessage): ViewMessage {
  return {
    localId: `server-${message.id}`,
    id: message.id,
    role: message.role,
    content: message.role === 'user' ? message.content : i18n.tr(message.content),
    responseMode: message.response_mode,
    topic: message.topic,
    can_create_ticket: message.can_create_ticket,
    replyToId: message.reply_to_id,
    status: 'sent',
  }
}

async function loadSession() {
  initialLoading.value = true
  loadError.value = false
  try {
    const session = await getSupportSession(supportApiLanguage(i18n.lang))
    conversationId.value = session.conversation_id
    serviceMode.value = session.service_mode
    messages.value = session.messages.map(fromServer)
    tickets.value = session.tickets
    await scrollBottom()
  } catch {
    loadError.value = true
  } finally {
    initialLoading.value = false
  }
}

function makeClientMessageId() {
  return `support-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || sending.value || initialLoading.value) return
  inputText.value = ''
  const message: ViewMessage = {
    localId: makeClientMessageId(),
    role: 'user',
    content: text.slice(0, 1000),
    status: 'sending',
    clientMessageId: makeClientMessageId(),
  }
  messages.value.push(message)
  await scrollBottom()
  await deliverMessage(message)
}

async function sendQuick(question: string) {
  if (sending.value) return
  inputText.value = question
  await onSend()
}

async function deliverMessage(message: ViewMessage) {
  sending.value = true
  message.status = 'sending'
  try {
    const response = await sendMessage({
      message: message.content,
      conversationId: conversationId.value,
      clientMessageId: message.clientMessageId || makeClientMessageId(),
      lang: supportApiLanguage(i18n.lang),
    })
    message.status = 'sent'
    conversationId.value = response.conversation_id
    serviceMode.value = response.service_mode
    const duplicate = messages.value.some(item => item.id === response.message.id)
    if (!duplicate) messages.value.push(fromServer(response.message))
  } catch {
    message.status = 'failed'
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

async function retryMessage(message: ViewMessage) {
  if (sending.value || message.status !== 'failed') return
  await deliverMessage(message)
}

function precedingQuestion(index: number) {
  for (let position = index - 1; position >= 0; position -= 1) {
    if (messages.value[position].role === 'user') return messages.value[position].content
  }
  return t('supportTicketDefaultSubject')
}

async function createTicket(message: ViewMessage, index: number) {
  if (!conversationId.value || creatingTicketId.value) return
  creatingTicketId.value = message.localId
  const question = precedingQuestion(index)
  try {
    const response = await createSupportTicket({
      conversationId: conversationId.value,
      sourceMessageId: message.id,
      subject: question.slice(0, 120),
      description: question.slice(0, 2000),
      category: message.topic || 'other',
      lang: supportApiLanguage(i18n.lang),
    })
    message.ticket = response.ticket
    tickets.value = [response.ticket, ...tickets.value.filter(item => item.id !== response.ticket.id)]
    uni.showToast({ title: t('supportTicketCreated'), icon: 'success' })
  } catch {
    uni.showToast({ title: t('supportTicketCreateFailed'), icon: 'none' })
  } finally {
    creatingTicketId.value = ''
    await scrollBottom()
  }
}

async function refreshTickets() {
  try {
    const response = await listSupportTickets()
    tickets.value = response.items
  } catch {
    uni.showToast({ title: t('supportTicketRefreshFailed'), icon: 'none' })
  }
}

function ticketStatusLabel(status: SupportTicketStatus) {
  return t(`supportTicketStatus_${status}`)
}

async function scrollBottom() {
  await nextTick()
  scrollToId.value = ''
  await nextTick()
  scrollToId.value = 'msg-bottom'
}

onMounted(loadSession)

// Assistant replies are localized by the service, rather than translated in
// the template. Refresh the session immediately when the app language changes
// so replies already on screen do not remain in the previous language.
watch(() => i18n.lang, () => {
  void loadSession()
})
</script>

<style lang="scss" scoped>
.page { height: 100vh; background: var(--bg); display: flex; flex-direction: column; overflow: hidden; }
.service-banner { margin: 16rpx 28rpx 0; padding: 18rpx 22rpx; border: 1rpx solid var(--border); border-radius: 20rpx; background: var(--card); display: flex; align-items: center; gap: 16rpx; }
.service-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: #1f9d68; box-shadow: 0 0 0 8rpx rgba(31, 157, 104, .1); }
.service-dot.ai_assisted { background: #0ea5a8; box-shadow: 0 0 0 8rpx rgba(14, 165, 168, .1); }
.service-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.service-title { color: var(--text); font-size: 26rpx; font-weight: 700; }
.ticket-count { flex-shrink: 0; color: var(--primary); font-size: 22rpx; padding: 10rpx 14rpx; border-radius: 16rpx; background: var(--primary-soft); }
.tickets-strip { flex-shrink: 0; width: 100%; padding: 14rpx 0 2rpx; }
.tickets-row { display: inline-flex; gap: 14rpx; padding: 0 28rpx; }
.ticket-card { width: 280rpx; padding: 16rpx 18rpx; border-radius: 18rpx; background: var(--card); border: 1rpx solid var(--border); display: flex; flex-direction: column; gap: 6rpx; }
.ticket-no { color: var(--text); font-size: 23rpx; font-weight: 700; }
.ticket-status { color: #a56512; font-size: 21rpx; }
.ticket-subject { color: var(--text-dim); font-size: 21rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.state-box { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20rpx; color: var(--text-dim); font-size: 25rpx; }
.spinner { width: 36rpx; height: 36rpx; border: 4rpx solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: rotate .8s linear infinite; }
.retry-pill { padding: 12rpx 28rpx; border-radius: 28rpx; color: var(--primary); border: 1rpx solid var(--primary); }
.chat-body { flex: 1; min-height: 0; padding: 24rpx 28rpx 12rpx; box-sizing: border-box; }
.scroll-anchor { height: 22rpx; }
.msg-row { display: flex; align-items: flex-start; gap: 16rpx; margin-bottom: 26rpx; }
.msg-row.user { flex-direction: row-reverse; }
.avatar { width: 64rpx; height: 64rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 21rpx; font-weight: 800; flex-shrink: 0; }
.service-avatar { background: #15373a; color: #fff; }
.user-avatar { background: var(--bg-2); color: var(--text); }
.assistant-stack, .user-stack { max-width: 76%; display: flex; flex-direction: column; align-items: flex-start; gap: 10rpx; }
.user-stack { align-items: flex-end; }
.bubble { padding: 20rpx 26rpx; border-radius: 24rpx; font-size: 27rpx; line-height: 1.65; word-break: break-word; white-space: pre-wrap; }
.assistant-bubble { background: var(--card); color: var(--text); border-top-left-radius: 8rpx; box-shadow: 0 3rpx 14rpx var(--shadow); }
.user-bubble { background: var(--primary); color: #fff; border-top-right-radius: 8rpx; }
.delivery-note { color: var(--text-dim); font-size: 20rpx; padding: 0 8rpx; }
.delivery-note.failed { color: #d14343; }
.quick-scroll { width: 100%; }
.quick-row { display: inline-flex; gap: 12rpx; padding: 2rpx 2rpx 8rpx; }
.quick-pill { padding: 12rpx 20rpx; border-radius: 24rpx; border: 1rpx solid var(--border); background: var(--card); color: var(--primary); font-size: 22rpx; white-space: nowrap; }
.ticket-action { padding: 12rpx 20rpx; border-radius: 24rpx; border: 1rpx solid var(--primary); color: var(--primary); font-size: 23rpx; font-weight: 600; }
.ticket-action.disabled { opacity: .5; }
.created-ticket { width: 100%; box-sizing: border-box; padding: 18rpx 20rpx; border-radius: 18rpx; background: #fff8eb; border: 1rpx solid #f0d29a; display: flex; flex-wrap: wrap; align-items: baseline; gap: 8rpx 14rpx; }
.created-ticket-title { color: #775019; font-size: 22rpx; }
.created-ticket-no { color: #3f2c0f; font-size: 24rpx; font-weight: 700; }
.created-ticket-status { color: #a56512; font-size: 21rpx; }
.typing { display: flex; gap: 8rpx; padding-top: 28rpx; padding-bottom: 28rpx; }
.typing-dot { width: 10rpx; height: 10rpx; border-radius: 50%; background: var(--text-dim); animation: pulse 1s infinite ease-in-out; }
.typing-dot:nth-child(2) { animation-delay: .15s; }
.typing-dot:nth-child(3) { animation-delay: .3s; }
.privacy-tip { flex-shrink: 0; padding: 8rpx 32rpx 0; color: var(--text-dim); background: var(--card); font-size: 19rpx; line-height: 1.4; }
.input-bar { flex-shrink: 0; display: flex; gap: 14rpx; padding: 14rpx 28rpx; background: var(--card); border-top: 1rpx solid var(--border); }
.msg-input { flex: 1; height: 72rpx; line-height: 72rpx; background: var(--bg); border-radius: 36rpx; padding: 0 26rpx; color: var(--text); font-size: 27rpx; }
.msg-ph { color: var(--text-dim); }
.send-btn { min-width: 104rpx; height: 72rpx; border-radius: 36rpx; background: var(--primary); color: #fff; font-size: 26rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.send-btn.disabled { opacity: .4; }
@keyframes rotate { to { transform: rotate(360deg); } }
@keyframes pulse { 0%, 60%, 100% { opacity: .25; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-5rpx); } }
</style>

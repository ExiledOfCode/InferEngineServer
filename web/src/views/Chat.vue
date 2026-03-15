<template>
  <div class="chat-container">
    <div class="sidebar">
      <div class="new-chat" @click="handleNewChat"><el-icon><Plus /></el-icon><span>新对话</span></div>
      <div class="engine-status" :class="{ online: !!chatStore.inferenceStatus?.running }">
        推理引擎: {{ chatStore.inferenceStatus?.running ? '在线' : '离线' }}
      </div>
      <div class="conversation-list">
        <div v-for="conv in chatStore.conversations" :key="conv.id" class="conversation-item" :class="{ active: chatStore.currentConversation?.id === conv.id }" @click="chatStore.selectConversation(conv.id)">
          <el-icon><ChatDotRound /></el-icon><span class="conv-title">{{ conv.title }}</span>
          <el-icon class="delete-btn" @click.stop="handleDelete(conv.id)"><Delete /></el-icon>
        </div>
      </div>
      <div class="user-info"><el-icon><User /></el-icon><span>{{ authStore.user?.username }}</span><el-icon class="logout-btn" @click="handleLogout"><SwitchButton /></el-icon></div>
    </div>
    <div class="main-content">
      <div class="message-list" ref="messageListRef">
        <div v-if="chatStore.messages.length === 0" class="welcome"><h1>有什么可以帮忙的？</h1></div>
        <div v-for="msg in chatStore.messages" :key="msg.id" class="message" :class="msg.role">
          <div class="message-avatar"><el-icon v-if="msg.role === 'user'"><User /></el-icon><el-icon v-else><Monitor /></el-icon></div>
          <div class="message-content">{{ msg.content }}</div>
        </div>
        <div v-if="chatStore.loading" class="message assistant"><div class="message-avatar"><el-icon><Monitor /></el-icon></div><div class="message-content loading"><span></span><span></span><span></span></div></div>
      </div>
      <div class="input-area"><div class="input-wrapper">
        <el-input v-model="inputMessage" type="textarea" :rows="1" :autosize="{ minRows: 1, maxRows: 5 }" placeholder="询问任何问题..." @keydown.enter.exact.prevent="handleSend" :disabled="chatStore.loading" />
        <el-button type="primary" :icon="Promotion" circle @click="handleSend" :disabled="!inputMessage.trim() || chatStore.loading" />
      </div></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Promotion } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()
const inputMessage = ref('')
const messageListRef = ref(null)

function formatErrorMessage(error, fallback) {
  const detail = error?.detail || fallback
  const status = error?.status ? `HTTP ${error.status}` : ''
  const method = error?.method ? String(error.method).toUpperCase() : ''
  const endpoint = error?.baseURL || error?.url ? `${method} ${error?.baseURL || ''}${error?.url || ''}`.trim() : ''
  return [detail, status, endpoint].filter(Boolean).join(' | ')
}

onMounted(async () => {
  try {
    await chatStore.fetchConversations()
  } catch (e) {
    ElMessage.error(formatErrorMessage(e, '加载对话列表失败'))
  }
  try {
    const status = await chatStore.fetchInferenceStatus()
    if (!status?.running) {
      ElMessage.warning('推理引擎未运行，发送消息可能超时或失败。')
    }
  } catch (e) {
    ElMessage.warning(formatErrorMessage(e, '无法获取推理状态'))
  }
})
watch(() => chatStore.messages.length, () => nextTick(() => { if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight }))

async function handleNewChat() { await chatStore.createConversation() }
async function handleSend() { const c = inputMessage.value.trim(); if (!c || chatStore.loading) return; inputMessage.value = ''; await chatStore.sendMessage(c) }
async function handleDelete(id) { try { await ElMessageBox.confirm('确定删除？', '提示', { type: 'warning' }); await chatStore.deleteConversation(id); ElMessage.success('已删除') } catch {} }
function handleLogout() { authStore.logout(); router.push('/login') }
</script>

<style scoped>
.chat-container { display: flex; height: 100vh; background: var(--main-bg); }
.sidebar { width: 260px; background: var(--sidebar-bg); display: flex; flex-direction: column; padding: 10px; }
.new-chat { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--sidebar-border); border-radius: 8px; cursor: pointer; color: var(--text-primary); }
.new-chat:hover { background: var(--sidebar-hover); }
.engine-status { margin-top: 10px; padding: 8px 12px; border-radius: 8px; font-size: 12px; color: #D1D5DB; background: #3A3B42; border: 1px solid #4B5563; }
.engine-status.online { color: #D1FAE5; background: #064E3B; border-color: #10B981; }
.conversation-list { flex: 1; overflow-y: auto; margin-top: 10px; }
.conversation-item { display: flex; align-items: center; gap: 10px; padding: 12px; border-radius: 8px; cursor: pointer; color: var(--text-primary); }
.conversation-item:hover, .conversation-item.active { background: var(--sidebar-hover); }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.delete-btn { opacity: 0; }
.conversation-item:hover .delete-btn { opacity: 1; }
.user-info { display: flex; align-items: center; gap: 10px; padding: 12px; border-top: 1px solid var(--sidebar-border); color: var(--text-primary); }
.user-info span { flex: 1; }
.logout-btn { cursor: pointer; }
.main-content { flex: 1; display: flex; flex-direction: column; }
.message-list { flex: 1; overflow-y: auto; padding: 20px 0; }
.welcome { height: 100%; display: flex; justify-content: center; align-items: center; }
.welcome h1 { color: var(--text-primary); font-size: 32px; }
.message { display: flex; padding: 20px 15%; gap: 20px; }
.message.user { background: var(--message-user-bg); }
.message.assistant { background: var(--message-ai-bg); }
.message-avatar { width: 36px; height: 36px; border-radius: 4px; display: flex; justify-content: center; align-items: center; font-size: 20px; color: white; }
.message.user .message-avatar { background: #5436DA; }
.message.assistant .message-avatar { background: var(--accent-color); }
.message-content { flex: 1; color: var(--text-primary); line-height: 1.7; white-space: pre-wrap; }
.message-content.loading { display: flex; gap: 4px; }
.message-content.loading span { width: 8px; height: 8px; background: var(--text-secondary); border-radius: 50%; animation: loading 1.4s infinite; }
.message-content.loading span:nth-child(1) { animation-delay: -0.32s; }
.message-content.loading span:nth-child(2) { animation-delay: -0.16s; }
@keyframes loading { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
.input-area { padding: 20px 15%; }
.input-wrapper { display: flex; align-items: flex-end; gap: 10px; background: #40414F; border-radius: 12px; padding: 12px; }
.input-wrapper :deep(.el-textarea__inner) { background: transparent; border: none; box-shadow: none; color: var(--text-primary); }
.input-wrapper :deep(.el-button) { background: var(--accent-color); border-color: var(--accent-color); }
</style>

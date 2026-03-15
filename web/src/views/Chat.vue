<template>
  <div class="chat-shell">
    <aside class="chat-sidebar" :class="{ show: mobileSidebarOpen }">
      <div class="sidebar-header">
        <button class="new-chat-btn" @click="handleNewChat">
          <el-icon><Plus /></el-icon>
          <span>新对话</span>
        </button>
        <button class="sidebar-close" @click="mobileSidebarOpen = false">
          <el-icon><CloseBold /></el-icon>
        </button>
      </div>

      <div class="engine-status" :class="{ online: !!chatStore.inferenceStatus?.running }">
        <span class="status-dot"></span>
        <span>推理引擎 {{ chatStore.inferenceStatus?.running ? '在线' : '离线' }}</span>
      </div>

      <div class="conversation-list">
        <button
          v-for="conv in chatStore.conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: chatStore.currentConversation?.id === conv.id }"
          @click="handleSelectConversation(conv.id)"
        >
          <el-icon class="conv-icon"><ChatDotRound /></el-icon>
          <div class="conversation-text">
            <span class="conv-title">{{ conv.title || '新对话' }}</span>
            <span class="conv-time">{{ formatConversationTime(conv.updated_at || conv.created_at) }}</span>
          </div>
          <el-icon class="delete-btn" @click.stop="handleDelete(conv.id)"><Delete /></el-icon>
        </button>
      </div>

      <div class="user-panel">
        <div class="user-meta">
          <div class="avatar">{{ (authStore.user?.username || 'U').slice(0, 1).toUpperCase() }}</div>
          <div class="name-block">
            <span class="name">{{ authStore.user?.username }}</span>
            <span class="role">Chat User</span>
          </div>
        </div>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <div v-if="mobileSidebarOpen" class="sidebar-mask" @click="mobileSidebarOpen = false"></div>

    <section class="chat-main">
      <header class="chat-header">
        <button class="menu-btn" @click="mobileSidebarOpen = true">
          <el-icon><Menu /></el-icon>
        </button>
        <div class="header-meta">
          <h1>{{ currentTitle }}</h1>
          <p>ChatGPT 风格界面 · {{ chatStore.inferenceStatus?.running ? '模型已连接' : '等待模型连接' }}</p>
        </div>
        <button class="ghost-btn" @click="handleNewChat">新建</button>
      </header>

      <main class="message-list" ref="messageListRef">
        <div class="message-track">
          <div v-if="chatStore.messages.length === 0" class="welcome-card">
            <h2>有什么可以帮忙的？</h2>
            <p>输入问题后，系统会以对话模式响应。你也可以试试下面几个提示。</p>
            <div class="prompt-grid">
              <button class="prompt-item" @click="fillPrompt('请用三点总结这段内容的核心结论')">总结一段文本</button>
              <button class="prompt-item" @click="fillPrompt('帮我规划一个 7 天学习计划，每天 1 小时')">生成学习计划</button>
              <button class="prompt-item" @click="fillPrompt('解释一下这个报错可能的原因和排查步骤')">调试报错问题</button>
              <button class="prompt-item" @click="fillPrompt('把这段描述改写得更专业一点')">润色文字表达</button>
            </div>
          </div>

          <article
            v-for="msg in chatStore.messages"
            :key="msg.id"
            class="message-row"
            :class="msg.role"
          >
            <div v-if="msg.role !== 'user'" class="assistant-avatar">
              <el-icon><Monitor /></el-icon>
            </div>
            <div class="message-body" :class="msg.role">
              {{ msg.content }}
            </div>
          </article>

          <article v-if="chatStore.loading" class="message-row assistant">
            <div class="assistant-avatar">
              <el-icon><Monitor /></el-icon>
            </div>
            <div class="message-body assistant loading">
              <span></span><span></span><span></span>
            </div>
          </article>
        </div>
      </main>

      <footer class="composer-area">
        <div class="composer-box">
          <el-input
            ref="inputRef"
            v-model="inputMessage"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 8 }"
            placeholder="给 ChatGPT 发消息"
            :disabled="chatStore.loading"
            @keydown.enter.exact.prevent="handleSend"
          />
          <button
            class="send-btn"
            :disabled="!inputMessage.trim() || chatStore.loading"
            @click="handleSend"
          >
            <el-icon><Promotion /></el-icon>
          </button>
        </div>
        <p class="composer-note">模型可能会犯错，请核对重要信息。</p>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Promotion } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()
const inputMessage = ref('')
const inputRef = ref(null)
const messageListRef = ref(null)
const mobileSidebarOpen = ref(false)

const currentTitle = computed(() => chatStore.currentConversation?.title || '新对话')

function formatErrorMessage(error, fallback) {
  const detail = error?.detail || fallback
  const status = error?.status ? `HTTP ${error.status}` : ''
  const method = error?.method ? String(error.method).toUpperCase() : ''
  const endpoint = error?.baseURL || error?.url ? `${method} ${error?.baseURL || ''}${error?.url || ''}`.trim() : ''
  return [detail, status, endpoint].filter(Boolean).join(' | ')
}

function formatConversationTime(raw) {
  if (!raw) return ''
  const value = new Date(raw)
  if (Number.isNaN(value.getTime())) return ''
  const now = new Date()
  const isToday = value.toDateString() === now.toDateString()
  if (isToday) {
    return `${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`
  }
  return `${value.getMonth() + 1}/${value.getDate()}`
}

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

function fillPrompt(text) {
  inputMessage.value = text
  nextTick(() => {
    if (inputRef.value?.focus) {
      inputRef.value.focus()
    }
  })
}

function handleWindowResize() {
  if (window.innerWidth > 960) {
    mobileSidebarOpen.value = false
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleWindowResize)
  try {
    await chatStore.fetchConversations()
  } catch (e) {
    ElMessage.error(formatErrorMessage(e, '加载对话列表失败'))
  }
  try {
    const status = await chatStore.fetchInferenceStatus()
    if (!status?.running) {
      ElMessage.warning('推理引擎未运行，首次回答可能较慢。')
    }
  } catch (e) {
    ElMessage.warning(formatErrorMessage(e, '无法获取推理状态'))
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
})

watch(
  () => chatStore.messages.length,
  () => nextTick(scrollToBottom)
)

watch(
  () => chatStore.currentConversation?.id,
  () => {
    if (window.innerWidth <= 960) {
      mobileSidebarOpen.value = false
    }
  }
)

async function handleSelectConversation(id) {
  await chatStore.selectConversation(id)
}

async function handleNewChat() {
  await chatStore.createConversation()
  nextTick(() => inputRef.value?.focus && inputRef.value.focus())
}

async function handleSend() {
  const content = inputMessage.value.trim()
  if (!content || chatStore.loading) return
  inputMessage.value = ''
  await chatStore.sendMessage(content)
  nextTick(() => inputRef.value?.focus && inputRef.value.focus())
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定删除这个对话吗？', '删除确认', { type: 'warning' })
    await chatStore.deleteConversation(id)
    ElMessage.success('已删除')
  } catch {
    // ignore cancel
  }
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.chat-shell {
  position: relative;
  display: flex;
  height: 100vh;
  background:
    radial-gradient(circle at 85% -10%, rgba(16, 163, 127, 0.12), transparent 38%),
    linear-gradient(180deg, #f8fafd 0%, #f5f7fb 100%);
}

.chat-sidebar {
  width: 282px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 12px;
  border-right: 1px solid var(--border-subtle);
  background: var(--surface-sidebar);
  z-index: 12;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.new-chat-btn {
  flex: 1;
  height: 42px;
  border-radius: 12px;
  border: 1px solid var(--border-strong);
  background: var(--surface-main);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-chat-btn:hover {
  background: #fdfefe;
  border-color: #aebad0;
}

.sidebar-close {
  display: none;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #f6f8fb;
  color: var(--text-secondary);
  cursor: pointer;
}

.engine-status {
  height: 38px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #f8fafc;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #9ca3af;
}

.engine-status.online {
  color: #0f766e;
  border-color: #8ee5c5;
  background: #ecfff8;
}

.engine-status.online .status-dot {
  background: var(--accent-color);
  box-shadow: 0 0 0 4px rgba(16, 163, 127, 0.18);
}

.conversation-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 3px;
}

.conversation-item {
  width: 100%;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease;
}

.conversation-item:hover {
  background: var(--surface-sidebar-hover);
}

.conversation-item.active {
  background: #dce4f0;
}

.conv-icon {
  color: var(--text-muted);
  font-size: 16px;
}

.conversation-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-title {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-time {
  color: var(--text-muted);
  font-size: 12px;
}

.delete-btn {
  color: #9aa3b4;
  opacity: 0;
  transition: opacity 0.2s ease, color 0.2s ease;
}

.conversation-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: var(--danger-color);
}

.user-panel {
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: #f7f9fc;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.user-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(140deg, #2f4a80, #1f2f52);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.name-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.role {
  color: var(--text-muted);
  font-size: 11px;
}

.logout-btn {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 10px;
  color: var(--text-secondary);
  background: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.logout-btn:hover {
  background: #e9eef6;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  height: 62px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(8px);
  padding: 0 22px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.menu-btn {
  display: none;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #f7f9fc;
  color: var(--text-secondary);
  cursor: pointer;
}

.header-meta {
  flex: 1;
  min-width: 0;
}

.header-meta h1 {
  font-size: 17px;
  color: var(--text-primary);
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-meta p {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 12px;
}

.ghost-btn {
  min-width: 64px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #fff;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  border-color: #b8c3d5;
}

.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 0 16px;
}

.message-track {
  width: min(920px, calc(100% - 32px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.welcome-card {
  border: 1px solid var(--border-subtle);
  border-radius: 20px;
  background: var(--surface-main);
  box-shadow: var(--shadow-card);
  padding: 28px 26px;
}

.welcome-card h2 {
  font-size: 30px;
  line-height: 1.2;
  color: #111827;
  font-weight: 680;
}

.welcome-card p {
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 15px;
}

.prompt-grid {
  margin-top: 20px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.prompt-item {
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 12px 14px;
  background: #f9fbfe;
  color: var(--text-primary);
  text-align: left;
  font-size: 13px;
  line-height: 1.45;
  cursor: pointer;
  transition: all 0.2s ease;
}

.prompt-item:hover {
  border-color: #b7c6dc;
  background: #ffffff;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-row.user {
  justify-content: flex-end;
}

.assistant-avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, #10a37f, #0f7d62);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.message-body {
  max-width: min(84%, 780px);
  border-radius: 16px;
  padding: 12px 14px;
  line-height: 1.75;
  font-size: 15px;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-body.assistant {
  background: var(--surface-ai-message);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.message-body.user {
  background: var(--surface-user-message);
  border: 1px solid #d2d9e6;
  color: #1a2233;
}

.message-body.loading {
  min-width: 64px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.message-body.loading span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  animation: pulse 1.3s infinite ease-in-out;
}

.message-body.loading span:nth-child(2) {
  animation-delay: 0.15s;
}

.message-body.loading span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes pulse {
  0%,
  80%,
  100% {
    opacity: 0.25;
    transform: scale(0.85);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.composer-area {
  padding: 12px 0 16px;
  border-top: 1px solid var(--border-subtle);
  background: rgba(255, 255, 255, 0.95);
}

.composer-box {
  width: min(920px, calc(100% - 32px));
  margin: 0 auto;
  border: 1px solid var(--border-strong);
  border-radius: 18px;
  background: var(--surface-input);
  box-shadow: var(--shadow-card);
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px 10px 10px 14px;
}

.composer-box :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.55;
  padding: 2px 0 4px;
}

.composer-box :deep(.el-textarea__inner::placeholder) {
  color: #9aa4b2;
}

.send-btn {
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 11px;
  background: var(--accent-color);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  transition: background 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-color-strong);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.composer-note {
  width: min(920px, calc(100% - 32px));
  margin: 8px auto 0;
  color: var(--text-muted);
  text-align: center;
  font-size: 12px;
}

.sidebar-mask {
  display: none;
}

@media (max-width: 960px) {
  .chat-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    height: 100vh;
    transform: translateX(-108%);
    transition: transform 0.25s ease;
    box-shadow: var(--shadow-float);
  }

  .chat-sidebar.show {
    transform: translateX(0);
  }

  .sidebar-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(13, 18, 30, 0.45);
    z-index: 10;
  }

  .menu-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .chat-header {
    padding: 0 14px;
  }

  .ghost-btn {
    display: none;
  }

  .message-track,
  .composer-box,
  .composer-note {
    width: calc(100% - 20px);
  }

  .prompt-grid {
    grid-template-columns: 1fr;
  }

  .message-body {
    max-width: 100%;
  }
}
</style>

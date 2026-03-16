<template>
  <div class="chat-shell">
    <aside class="chat-sidebar" :class="{ show: mobileSidebarOpen, collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <button class="new-chat-btn" :disabled="chatStore.creatingConversation" @click="handleNewChat">
          <el-icon><Plus /></el-icon>
          <span v-if="!sidebarCollapsed">新对话</span>
        </button>
        <button class="sidebar-toggle" title="收起侧边栏" @click="toggleSidebar">
          <el-icon v-if="sidebarCollapsed"><Expand /></el-icon>
          <el-icon v-else><Fold /></el-icon>
        </button>
        <button class="sidebar-close" @click="mobileSidebarOpen = false">
          <el-icon><CloseBold /></el-icon>
        </button>
      </div>

      <div class="engine-status" :class="{ online: !!chatStore.inferenceStatus?.running }">
        <span class="status-dot"></span>
        <span v-if="!sidebarCollapsed">推理引擎 {{ chatStore.inferenceStatus?.running ? '在线' : '离线' }}</span>
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
          <div v-if="!sidebarCollapsed" class="conversation-text">
            <span class="conv-title">{{ conv.title || '新对话' }}</span>
            <span class="conv-time">{{ formatConversationTime(conv.updated_at || conv.created_at) }}</span>
          </div>
          <el-icon v-if="!sidebarCollapsed" class="delete-btn" @click.stop="handleDelete(conv.id)"><Delete /></el-icon>
        </button>
      </div>

      <div class="user-panel" :class="{ collapsed: sidebarCollapsed }">
        <div v-if="!sidebarCollapsed" class="user-meta">
          <div class="avatar">{{ (authStore.user?.username || 'U').slice(0, 1).toUpperCase() }}</div>
          <div class="name-block">
            <span class="name">{{ authStore.user?.username }}</span>
            <span class="role">Chat User</span>
          </div>
        </div>
        <div v-else class="avatar">{{ (authStore.user?.username || 'U').slice(0, 1).toUpperCase() }}</div>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <div v-if="mobileSidebarOpen" class="sidebar-mask" @click="mobileSidebarOpen = false"></div>

    <section class="chat-main">
      <header class="chat-header">
        <div class="header-meta">
          <h1>{{ currentTitle }}</h1>
          <p>江屿大模型 · {{ chatStore.inferenceStatus?.running ? '模型已连接' : '等待模型连接' }}</p>
        </div>
        <div class="header-actions">
          <button class="trace-toggle-btn" @click="toggleTraceSidebar">
            {{ traceSidebarCollapsed ? '展开过程' : '收起过程' }}
          </button>
        </div>
      </header>

      <main class="message-list" ref="messageListRef">
        <div class="message-track">
          <div v-if="chatStore.messages.length === 0" class="welcome-card">
            <h2>有什么可以帮忙的？</h2>
            <p>欢迎使用江屿大模型，输入你的问题开始对话。</p>
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

          <article
            v-if="chatStore.loading && chatStore.currentConversation?.id === chatStore.loadingConversationId"
            class="message-row assistant"
          >
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
            placeholder="给 江屿大模型 发消息"
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

    <aside
      class="trace-sidebar"
      :class="{ collapsed: traceSidebarCollapsed }"
      :style="traceSidebarStyle"
    >
      <div
        v-if="!traceSidebarCollapsed"
        class="trace-resize-handle"
        @mousedown="startTraceResize"
      ></div>
      <div class="trace-sidebar-header">
        <h3 v-if="!traceSidebarCollapsed">推理引擎过程</h3>
        <button class="trace-sidebar-toggle" @click="toggleTraceSidebar">
          <el-icon v-if="traceSidebarCollapsed"><Expand /></el-icon>
          <el-icon v-else><Fold /></el-icon>
        </button>
      </div>

      <div v-if="!traceSidebarCollapsed" class="trace-sidebar-body">
        <div class="trace-summary">
          <span class="trace-state-label">状态</span>
          <span class="trace-state-value" :class="traceStateClass">{{ traceStateText }}</span>
        </div>
        <div class="trace-summary">
          <span class="trace-state-label">请求ID</span>
          <span class="trace-state-value">{{ activeTrace?.request_id || '-' }}</span>
        </div>

        <div v-if="traceSteps.length === 0" class="trace-empty">
          <p v-if="chatStore.loading">正在等待推理埋点...</p>
          <p v-else>发送消息后，这里会显示 Tokenization / Encoding / Inference / Sampling / Decode。</p>
        </div>

        <section v-for="step in traceSteps" :key="step.id" class="trace-step">
          <div class="trace-step-head">
            <div class="trace-step-title">{{ step.title || step.id }}</div>
            <div v-if="step.duration_ms !== undefined && step.duration_ms !== null" class="trace-step-duration">
              {{ formatDuration(step.duration_ms) }}
            </div>
          </div>

          <template v-if="step.id === 'tokenization'">
            <div class="trace-field">
              <span class="label">输入文本</span>
              <pre class="value">{{ step.input_text || '-' }}</pre>
            </div>
            <div class="trace-field">
              <span class="label">Tokens ({{ step.token_count || 0 }})</span>
              <div class="token-list">
                <span v-for="(token, idx) in (step.tokens_preview || [])" :key="`${step.id}-token-${idx}`" class="token-chip">{{ token }}</span>
              </div>
            </div>
          </template>

          <template v-else-if="step.id === 'encoding'">
            <div class="trace-field">
              <span class="label">Token IDs ({{ step.token_count || 0 }})</span>
              <pre class="value">{{ formatTokenIds(step.token_ids_preview) }}</pre>
            </div>
          </template>

          <template v-else-if="step.id === 'transformer'">
            <div class="trace-field">
              <span class="label">阶段</span>
              <pre class="value">{{ (step.operations || []).join(' → ') || 'attention → hidden_states → logits' }}</pre>
            </div>
            <div class="trace-field">
              <span class="label">Qwen2 逻辑流程图</span>
              <div class="logic-flow">
                <div class="logic-main-row">
                  <div class="logic-node logic-node-input">
                    <span class="logic-node-title">x</span>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-node">
                    <span class="logic-node-title">RMSNorm</span>
                    <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'rmsnorm1')) }}</span>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-block">
                    <div class="logic-block-head">
                      <span class="logic-block-title">Attention</span>
                      <span class="logic-block-time">{{ formatDuration(logicalNodeDuration(step, 'attention')) }}</span>
                    </div>
                    <div class="logic-sub-row">
                      <div class="logic-parallel-group">
                        <span class="logic-parallel-tag">并行</span>
                        <div class="logic-node logic-node-sub">
                          <span class="logic-node-title">Wq</span>
                          <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'wq')) }}</span>
                        </div>
                        <div class="logic-node logic-node-sub">
                          <span class="logic-node-title">Wk</span>
                          <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'wk')) }}</span>
                        </div>
                        <div class="logic-node logic-node-sub">
                          <span class="logic-node-title">Wv</span>
                          <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'wv')) }}</span>
                        </div>
                      </div>
                      <span class="logic-arrow logic-arrow-sub">↓</span>
                      <div class="logic-node logic-node-sub">
                        <span class="logic-node-title">RoPE</span>
                        <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'rope')) }}</span>
                      </div>
                      <span class="logic-arrow logic-arrow-sub">↓</span>
                      <div class="logic-node logic-node-sub">
                        <span class="logic-node-title">Attention(Q,K,V)</span>
                        <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'mha')) }}</span>
                      </div>
                      <span class="logic-arrow logic-arrow-sub">↓</span>
                      <div class="logic-node logic-node-sub">
                        <span class="logic-node-title">Wo</span>
                        <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'wo')) }}</span>
                      </div>
                    </div>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-node">
                    <span class="logic-node-title">Residual Add</span>
                    <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'residual1')) }}</span>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-node">
                    <span class="logic-node-title">RMSNorm</span>
                    <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'rmsnorm2')) }}</span>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-block">
                    <div class="logic-block-head">
                      <span class="logic-block-title">FFN (SwiGLU)</span>
                      <span class="logic-block-time">{{ formatDuration(logicalNodeDuration(step, 'ffn')) }}</span>
                    </div>
                    <div class="logic-sub-row">
                      <div class="logic-parallel-group">
                        <span class="logic-parallel-tag">并行</span>
                        <div class="logic-node logic-node-sub">
                          <span class="logic-node-title">W1</span>
                          <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'w1')) }}</span>
                        </div>
                        <div class="logic-node logic-node-sub">
                          <span class="logic-node-title">W3</span>
                          <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'w3')) }}</span>
                        </div>
                      </div>
                      <span class="logic-arrow logic-arrow-sub">↓</span>
                      <div class="logic-node logic-node-sub">
                        <span class="logic-node-title">SwiGLU</span>
                        <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'swiglu')) }}</span>
                      </div>
                      <span class="logic-arrow logic-arrow-sub">↓</span>
                      <div class="logic-node logic-node-sub">
                        <span class="logic-node-title">W2</span>
                        <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'w2')) }}</span>
                      </div>
                    </div>
                  </div>
                  <span class="logic-arrow">↓</span>

                  <div class="logic-node">
                    <span class="logic-node-title">Residual Add</span>
                    <span class="logic-node-time">{{ formatDuration(logicalNodeDuration(step, 'residual2')) }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="trace-field" v-if="(step.operator_profile || []).length > 0">
              <span class="label">算子耗时 (Top 12)</span>
              <div class="op-table">
                <div class="op-row op-head">
                  <span>算子</span>
                  <span>总耗时</span>
                  <span>次数</span>
                  <span>平均</span>
                </div>
                <div
                  v-for="(item, idx) in (step.operator_profile || []).slice(0, 12)"
                  :key="`${step.id}-op-${idx}-${item.name}`"
                  class="op-row"
                >
                  <span>{{ item.name }}</span>
                  <span>{{ formatDuration(item.total_ms) }}</span>
                  <span>{{ item.calls || 0 }}</span>
                  <span>{{ formatDuration(item.avg_ms) }}</span>
                </div>
              </div>
            </div>
          </template>

          <template v-else-if="step.id === 'sampling'">
            <div class="trace-field">
              <span class="label">采样器</span>
              <pre class="value">{{ step.sampler || 'argmax' }}</pre>
            </div>
            <div class="trace-field" v-if="(step.selected_tokens || []).length > 0">
              <span class="label">已选 token</span>
              <div class="sample-list">
                <span
                  v-for="item in (step.selected_tokens || []).slice(-8)"
                  :key="`${step.id}-${item.index}-${item.token_id}`"
                  class="sample-item"
                >
                  #{{ item.index || '-' }} → {{ item.token || '' }} ({{ item.token_id ?? '-' }})
                </span>
                <span v-if="samplingRemainingCount(step) > 0" class="sample-item sample-ellipsis">
                  ... 省略 {{ samplingRemainingCount(step) }} 个 token
                </span>
              </div>
            </div>
          </template>

          <template v-else-if="step.id === 'decode'">
            <div class="trace-field">
              <span class="label">生成文本</span>
              <pre class="value">{{ step.generated_text_preview || '-' }}</pre>
            </div>
          </template>
        </section>
      </div>
    </aside>
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
const sidebarCollapsed = ref(false)
const traceSidebarCollapsed = ref(false)
const traceSidebarWidth = ref(460)
const traceSidebarMinWidth = 360
const traceSidebarMaxWidth = 860
const traceResizing = ref(false)
const traceResizeStartX = ref(0)
const traceResizeStartWidth = ref(460)
let statusTimer = null

const currentTitle = computed(() => chatStore.currentConversation?.title || '新对话')
const activeTrace = computed(() => chatStore.inferenceTrace || null)
const traceSteps = computed(() => (Array.isArray(activeTrace.value?.steps) ? activeTrace.value.steps : []))
const traceStateText = computed(() => {
  const state = String(activeTrace.value?.state || '').toLowerCase()
  if (state === 'running') return '运行中'
  if (state === 'completed') return '已完成'
  if (state === 'error') return '异常'
  return chatStore.loading ? '运行中' : '待机'
})
const traceStateClass = computed(() => {
  const state = String(activeTrace.value?.state || '').toLowerCase()
  if (state === 'running') return 'running'
  if (state === 'completed') return 'completed'
  if (state === 'error') return 'error'
  return 'idle'
})
const traceSidebarStyle = computed(() => {
  if (traceSidebarCollapsed.value) {
    return undefined
  }
  return { width: `${traceSidebarWidth.value}px` }
})
const logicalNodeOps = {
  rmsnorm1: ['attn.rmsnorm'],
  attention: ['attn.wq', 'attn.wk', 'attn.wv', 'attn.rope', 'attn.mha', 'attn.wo'],
  wq: ['attn.wq'],
  wk: ['attn.wk'],
  wv: ['attn.wv'],
  rope: ['attn.rope'],
  mha: ['attn.mha'],
  wo: ['attn.wo'],
  residual1: ['ffn.residual_add1'],
  rmsnorm2: ['ffn.rmsnorm'],
  ffn: ['ffn.w1', 'ffn.w3', 'ffn.swiglu', 'ffn.w2'],
  w1: ['ffn.w1'],
  w3: ['ffn.w3'],
  swiglu: ['ffn.swiglu'],
  w2: ['ffn.w2'],
  residual2: ['ffn.residual_add2']
}

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

function handleWindowResize() {
  if (window.innerWidth > 960) {
    mobileSidebarOpen.value = false
  } else {
    sidebarCollapsed.value = false
  }
  if (window.innerWidth <= 1100) {
    traceSidebarCollapsed.value = true
  }
}

function toggleSidebar() {
  if (window.innerWidth <= 960) {
    mobileSidebarOpen.value = !mobileSidebarOpen.value
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function toggleTraceSidebar() {
  traceSidebarCollapsed.value = !traceSidebarCollapsed.value
}

function formatTokenIds(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return '[]'
  }
  return `[${values.join(', ')}]`
}

function formatDuration(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value)) {
    return '-'
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`
  }
  if (value >= 100) {
    return `${value.toFixed(0)} ms`
  }
  if (value >= 10) {
    return `${value.toFixed(1)} ms`
  }
  return `${value.toFixed(2)} ms`
}

function startTraceResize(event) {
  if (window.innerWidth <= 1100 || traceSidebarCollapsed.value) {
    return
  }
  traceResizing.value = true
  traceResizeStartX.value = event.clientX
  traceResizeStartWidth.value = traceSidebarWidth.value
  document.body.style.userSelect = 'none'
}

function handleTraceResizeMove(event) {
  if (!traceResizing.value) return
  const delta = traceResizeStartX.value - event.clientX
  const next = traceResizeStartWidth.value + delta
  traceSidebarWidth.value = Math.max(traceSidebarMinWidth, Math.min(traceSidebarMaxWidth, next))
}

function stopTraceResize() {
  if (!traceResizing.value) return
  traceResizing.value = false
  document.body.style.userSelect = ''
}

function samplingRemainingCount(step) {
  const total = Number(step?.generated_token_count || 0)
  const shown = Array.isArray(step?.selected_tokens) ? step.selected_tokens.length : 0
  return total > shown ? total - shown : 0
}

function flowNodeDuration(step, opKeys) {
  const profile = Array.isArray(step?.operator_profile) ? step.operator_profile : []
  if (!Array.isArray(opKeys) || opKeys.length === 0 || profile.length === 0) {
    return undefined
  }
  const table = new Map(profile.map(item => [item.name, Number(item.total_ms || 0)]))
  return opKeys.reduce((acc, key) => acc + (table.get(key) || 0), 0)
}

function logicalNodeDuration(step, nodeId) {
  const keys = logicalNodeOps[nodeId]
  return flowNodeDuration(step, keys)
}

onMounted(async () => {
  window.addEventListener('resize', handleWindowResize)
  window.addEventListener('mousemove', handleTraceResizeMove)
  window.addEventListener('mouseup', stopTraceResize)
  handleWindowResize()
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
  try {
    await chatStore.fetchInferenceTrace()
  } catch {
    // ignore trace init error
  }

  statusTimer = window.setInterval(async () => {
    try {
      await chatStore.fetchInferenceStatus()
    } catch {
      // ignore polling error
    }
  }, 10000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  window.removeEventListener('mousemove', handleTraceResizeMove)
  window.removeEventListener('mouseup', stopTraceResize)
  stopTraceResize()
  if (statusTimer) {
    window.clearInterval(statusTimer)
    statusTimer = null
  }
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
  transition: width 0.22s ease, padding 0.22s ease;
}

.chat-sidebar.collapsed {
  width: 84px;
  padding: 14px 10px;
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

.new-chat-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-sidebar.collapsed .new-chat-btn {
  flex: unset;
  width: 42px;
  padding: 0;
}

.sidebar-toggle {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #f6f8fb;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.sidebar-toggle:hover {
  border-color: #bcc7d8;
  background: #f3f6fb;
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

.chat-sidebar.collapsed .engine-status {
  justify-content: center;
  padding: 0;
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

.chat-sidebar.collapsed .conversation-item {
  justify-content: center;
  padding: 10px 0;
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

.user-panel.collapsed {
  justify-content: center;
  padding: 8px 6px;
  flex-direction: column;
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

.header-meta {
  flex: 1;
  min-width: 0;
}

.header-actions {
  display: inline-flex;
  align-items: center;
}

.trace-toggle-btn {
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: #f6f8fc;
  color: var(--text-secondary);
  padding: 0 12px;
  font-size: 13px;
  cursor: pointer;
}

.trace-toggle-btn:hover {
  background: #edf3fa;
  border-color: #c7d0df;
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

.trace-sidebar {
  width: 460px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-subtle);
  background: #f7fafc;
  display: flex;
  flex-direction: column;
  transition: width 0.22s ease;
  position: relative;
}

.trace-sidebar.collapsed {
  width: 58px;
}

.trace-sidebar-header {
  min-height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.trace-sidebar-header h3 {
  font-size: 14px;
  color: #1f2937;
  font-weight: 650;
}

.trace-sidebar-toggle {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: #f1f5fb;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.trace-resize-handle {
  position: absolute;
  top: 0;
  left: -5px;
  width: 10px;
  height: 100%;
  cursor: col-resize;
  z-index: 2;
}

.trace-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 8px 10px;
  background: #ffffff;
}

.trace-state-label {
  color: var(--text-muted);
  font-size: 12px;
}

.trace-state-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.trace-state-value.running {
  color: #b45309;
}

.trace-state-value.completed {
  color: #166534;
}

.trace-state-value.error {
  color: #b91c1c;
}

.trace-empty {
  border: 1px dashed #c9d3e5;
  border-radius: 12px;
  padding: 14px 12px;
  color: var(--text-muted);
  background: #f9fbff;
  font-size: 12px;
  line-height: 1.6;
}

.trace-step {
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: #ffffff;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-step-title {
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
}

.trace-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.trace-step-duration {
  flex-shrink: 0;
  border: 1px solid #c9d7ec;
  border-radius: 999px;
  background: #f1f6ff;
  color: #1f3b64;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
}

.trace-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trace-field .label {
  font-size: 11px;
  color: var(--text-muted);
}

.trace-field .value {
  margin: 0;
  padding: 7px 8px;
  border-radius: 8px;
  background: #f4f7fd;
  border: 1px solid #e1e7f2;
  white-space: pre-wrap;
  word-break: break-word;
  color: #111827;
  font-size: 12px;
  line-height: 1.5;
}

.token-list,
.sample-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.token-chip,
.sample-item {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid #d7dfec;
  background: #f7fafe;
  color: #24324b;
  font-size: 11px;
  padding: 4px 8px;
}

.sample-ellipsis {
  background: #edf2fb;
  border-style: dashed;
}

.logic-flow {
  border: 1px solid #dce6f5;
  border-radius: 9px;
  background: #f8fbff;
  padding: 8px;
  overflow-x: hidden;
}

.logic-main-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 7px;
  width: 100%;
  padding-bottom: 2px;
}

.logic-arrow {
  align-self: center;
  color: #6f85a7;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.logic-arrow-sub {
  font-size: 11px;
}

.logic-node {
  width: 100%;
  border: 1px solid #d2deef;
  border-radius: 8px;
  background: #ffffff;
  padding: 6px 7px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
}

.logic-node-input {
  width: fit-content;
  min-width: 52px;
  padding-left: 14px;
  padding-right: 14px;
  align-self: center;
  align-items: center;
}

.logic-node-sub {
  width: 100%;
}

.logic-node-title {
  font-size: 11px;
  color: #1f304a;
  font-weight: 650;
  line-height: 1.25;
}

.logic-node-time {
  font-size: 11px;
  color: #375f8c;
  line-height: 1.2;
}

.logic-block {
  width: 100%;
  border: 1px solid #c9d7ef;
  border-radius: 8px;
  background: linear-gradient(180deg, #f4f8ff 0%, #ffffff 100%);
  padding: 7px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.logic-block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px dashed #d7e1f1;
  padding-bottom: 5px;
}

.logic-block-title {
  font-size: 11px;
  color: #1b3359;
  font-weight: 700;
}

.logic-block-time {
  font-size: 11px;
  color: #245189;
  font-weight: 600;
}

.logic-sub-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}

.logic-parallel-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
  padding: 5px 6px;
  border-radius: 8px;
  border: 1px dashed #cfdbef;
  background: rgba(231, 239, 252, 0.6);
}

.logic-parallel-group .logic-node-sub {
  width: auto;
  min-width: 88px;
  flex: 1 1 88px;
}

.logic-parallel-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: #d9e8ff;
  color: #244b7d;
  font-size: 10px;
  font-weight: 700;
}

.op-table {
  border: 1px solid #dde6f4;
  border-radius: 9px;
  background: #f8fbff;
  overflow: hidden;
}

.op-row {
  display: grid;
  grid-template-columns: minmax(110px, 1.6fr) 0.9fr 0.5fr 0.9fr;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border-top: 1px solid #e5ecf8;
  font-size: 11px;
  color: #22314a;
}

.op-row span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.op-row:first-child {
  border-top: none;
}

.op-row.op-head {
  font-weight: 700;
  color: #1d3357;
  background: #eef4ff;
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

  .sidebar-toggle {
    display: none;
  }

  .sidebar-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(13, 18, 30, 0.45);
    z-index: 10;
  }

  .chat-header {
    padding: 0 14px;
  }

  .message-track,
  .composer-box,
  .composer-note {
    width: calc(100% - 20px);
  }

  .message-body {
    max-width: 100%;
  }

  .trace-sidebar {
    display: none;
  }
}
</style>

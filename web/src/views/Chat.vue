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

      <div v-if="!sidebarCollapsed" class="conversation-section-label">最近</div>
      <div class="conversation-list">
        <div
          v-for="conv in chatStore.conversations"
          :key="conv.id"
          class="conversation-item"
          :class="{ active: chatStore.currentConversation?.id === conv.id }"
          role="button"
          tabindex="0"
          @click="handleSelectConversation(conv.id)"
          @keydown.enter.prevent="handleSelectConversation(conv.id)"
          @keydown.space.prevent="handleSelectConversation(conv.id)"
        >
          <el-icon class="conv-icon"><ChatDotRound /></el-icon>
          <div v-if="!sidebarCollapsed" class="conversation-text">
            <div class="conversation-title-row">
              <span class="conv-title">{{ conv.title || '新对话' }}</span>
              <span v-if="chatStore.isConversationPinned(conv.id)" class="pin-mark">置顶</span>
            </div>
            <span class="conv-time">{{ formatConversationTime(conv.updated_at || conv.created_at) }}</span>
          </div>
          <el-dropdown
            v-if="!sidebarCollapsed"
            class="conversation-menu"
            trigger="click"
            placement="bottom-end"
            @command="command => handleConversationCommand(command, conv)"
          >
            <button class="conversation-menu-btn" type="button" aria-label="对话操作" @click.stop>
              <span></span><span></span><span></span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="pin">
                  {{ chatStore.isConversationPinned(conv.id) ? '取消置顶' : '置顶' }}
                </el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
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

    <section class="chat-main" :class="{ 'empty-chat': chatStore.messages.length === 0 }">
      <header class="chat-header">
        <div class="header-meta">
          <h1>自研推理引擎对话平台</h1>
          <div class="current-model-line">
            <span class="current-model-name">{{ currentModelName || '未选择模型' }}</span>
            <div v-if="modelLoadingVisible" class="model-loading-inline">
              <div class="model-loading-inline-bar">
                <el-progress
                  :percentage="modelLoadingPercentage"
                  :stroke-width="6"
                  :show-text="false"
                />
              </div>
              <span class="model-loading-inline-text">
                {{ formatBytes(modelLoadingLoadedBytes) }} / {{ formatBytes(modelLoadingTotalBytes) }}
              </span>
            </div>
          </div>
        </div>
        <div class="header-actions">
          <div class="model-switcher">
            <span class="model-switcher-label">模型</span>
            <el-select
              v-model="selectedModelId"
              class="model-switcher-select"
              size="small"
              placeholder="选择模型"
              :disabled="chatStore.loading || chatStore.switchingModel"
              @change="handleModelChange"
            >
              <el-option
                v-for="model in availableModels"
                :key="model.id"
                :label="model.name"
                :value="model.id"
                :disabled="!model.ready"
              >
                <div class="model-option">
                  <span>{{ model.name }}</span>
                  <span class="model-option-meta">
                    {{ model.family || 'model' }}{{ model.ready ? '' : ' · 未就绪' }}
                  </span>
                </div>
              </el-option>
            </el-select>
          </div>
          <div class="think-toggle">
            <span class="think-toggle-label">Think</span>
            <el-switch
              v-model="thinkEnabled"
              size="small"
              inline-prompt
              active-text="开"
              inactive-text="关"
            />
          </div>
        </div>
      </header>

      <main class="message-list" ref="messageListRef">
        <div class="message-track">
          <div v-if="chatStore.messages.length === 0" class="welcome-card">
            <h2>今天有什么计划？</h2>
            <p>欢迎使用自研推理引擎对话平台，输入你的问题开始对话。</p>
          </div>

          <article
            v-for="msg in chatStore.messages"
            :key="msg.id"
            class="message-row"
            :class="[msg.role, { clickable: msg.role === 'assistant' && !!msg.inference_trace }]"
            @click="handleMessageClick(msg)"
          >
            <div v-if="msg.role !== 'user'" class="assistant-avatar">
              <el-icon><Monitor /></el-icon>
            </div>
            <div class="message-stack">
              <div class="message-body" :class="[msg.role, { thinking: msg.role === 'assistant' && !!msg.reasoning_content && thinkEnabled }]">
                <div class="message-content">
                  <template v-if="msg.role === 'assistant' && msg.reasoning_content && thinkEnabled">
                    <details class="assistant-think-panel">
                      <summary>思考过程</summary>
                      <pre class="assistant-think-text">{{ msg.reasoning_content }}</pre>
                    </details>
                    <div class="assistant-answer-text">{{ msg.content }}</div>
                  </template>
                  <template v-else>
                    {{ msg.content }}
                  </template>
                </div>
              </div>
              <div class="message-actions" @click.stop>
                <button
                  class="message-action-btn"
                  type="button"
                  aria-label="复制"
                  data-tooltip="复制"
                  @click.stop="handleCopyMessage(msg)"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="9" y="5" width="11" height="13" rx="2"></rect>
                    <rect x="4" y="10" width="11" height="9" rx="2"></rect>
                  </svg>
                </button>
                <button
                  class="message-action-btn"
                  :class="{ active: isMessageFeedbackActive(msg, 'like') }"
                  type="button"
                  aria-label="点赞"
                  data-tooltip="点赞"
                  @click.stop="handleMessageFeedback(msg, 'like')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M7 10v10"></path>
                    <path d="M7 10H4.8A1.8 1.8 0 0 0 3 11.8v6.4A1.8 1.8 0 0 0 4.8 20H7"></path>
                    <path d="M7 10l4.6-6.2c.7-.9 2.1-.5 2.1.7V9h4.6c1.2 0 2.1 1 1.9 2.2l-1 6.6A2.6 2.6 0 0 1 16.6 20H7"></path>
                  </svg>
                </button>
                <button
                  class="message-action-btn"
                  :class="{ active: isMessageFeedbackActive(msg, 'dislike') }"
                  type="button"
                  aria-label="点踩"
                  data-tooltip="点踩"
                  @click.stop="handleMessageFeedback(msg, 'dislike')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M17 14V4"></path>
                    <path d="M17 14h2.2a1.8 1.8 0 0 0 1.8-1.8V5.8A1.8 1.8 0 0 0 19.2 4H17"></path>
                    <path d="M17 14l-4.6 6.2c-.7.9-2.1.5-2.1-.7V15H5.7c-1.2 0-2.1-1-1.9-2.2l1-6.6A2.6 2.6 0 0 1 7.4 4H17"></path>
                  </svg>
                </button>
              </div>
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
          <button class="composer-plus-btn" type="button" title="新对话" @click="handleNewChat">
            <el-icon><Plus /></el-icon>
          </button>
          <el-input
            ref="inputRef"
            v-model="inputMessage"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 8 }"
            placeholder="有问题，尽管问"
            :disabled="composerStopping"
            @keydown.enter.exact.prevent="handleSend"
          />
          <button
            class="send-btn"
            :class="{ stopping: composerStopping, busy: chatStore.canceling }"
            :disabled="composerStopping ? chatStore.canceling : !inputMessage.trim()"
            :title="composerActionTitle"
            @click="handleComposerAction"
          >
            <span v-if="composerStopping" class="send-btn-stop-square" aria-hidden="true"></span>
            <el-icon v-else><Promotion /></el-icon>
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
          <p v-if="!engineTraceEnabled">管理员已关闭数据埋点，且当前会话没有历史埋点记录。</p>
          <p v-else-if="chatStore.loading">正在等待推理埋点...</p>
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
              <pre class="value trace-scrollbox trace-scrollbox--text">{{ step.input_text || '-' }}</pre>
            </div>
            <div class="trace-field">
              <span class="label">Tokens ({{ step.token_count || 0 }})</span>
              <div class="token-list trace-scrollbox trace-scrollbox--box trace-scrollbox--tokens">
                <span v-for="(token, idx) in (step.tokens_preview || [])" :key="`${step.id}-token-${idx}`" class="token-chip">{{ token }}</span>
              </div>
            </div>
          </template>

          <template v-else-if="step.id === 'encoding'">
            <div class="trace-field">
              <span class="label">Token IDs ({{ step.token_count || 0 }})</span>
              <pre class="value trace-scrollbox trace-scrollbox--text">{{ formatTokenIds(step.token_ids_preview) }}</pre>
            </div>
          </template>

          <template v-else-if="step.id === 'transformer'">
            <div class="trace-field">
              <span class="label">阶段</span>
              <pre class="value">{{ (step.operations || []).join(' → ') || 'attention → hidden_states → logits' }}</pre>
            </div>
            <div class="trace-field">
              <span class="label">{{ logicFlowLabel }}</span>
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
              <div class="sample-list trace-scrollbox trace-scrollbox--box trace-scrollbox--text">
                <span
                  v-for="item in (step.selected_tokens || [])"
                  :key="`${step.id}-${item.index}-${item.token_id}`"
                  class="sample-item"
                >
                  #{{ item.index || '-' }} → {{ item.token || '' }} ({{ item.token_id ?? '-' }})
                </span>
              </div>
            </div>
          </template>

          <template v-else-if="step.id === 'decode'">
            <div class="trace-field">
              <span class="label">生成文本</span>
              <pre class="value trace-scrollbox trace-scrollbox--text">{{ step.generated_text_preview || '-' }}</pre>
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
const selectedModelId = ref('')
const THINK_PREFERENCE_KEY = 'chat:show-think'
const thinkEnabled = ref(readThinkPreference())
let statusTimer = null

const availableModels = computed(() => (Array.isArray(chatStore.inferenceStatus?.available_models) ? chatStore.inferenceStatus.available_models : []))
const currentModelName = computed(() => chatStore.inferenceStatus?.current_model_name || '')
const currentModelFamily = computed(() => String(chatStore.inferenceStatus?.current_model_family || '').toLowerCase())
const engineTraceEnabled = computed(() => chatStore.inferenceStatus?.trace_enabled !== false)
const modelLoadingProgress = computed(() => chatStore.inferenceStatus?.model_loading_progress || null)
const modelLoadingState = computed(() => String(modelLoadingProgress.value?.state || '').toLowerCase())
const modelLoadingVisible = computed(() => ['starting', 'loading'].includes(modelLoadingState.value))
const modelLoadingLoadedBytes = computed(() => Number(modelLoadingProgress.value?.loaded_bytes || 0))
const modelLoadingTotalBytes = computed(() => Number(modelLoadingProgress.value?.total_bytes || 0))
const modelLoadingPercentage = computed(() => {
  const raw = Number(modelLoadingProgress.value?.percentage)
  if (Number.isFinite(raw)) {
    return Math.max(0, Math.min(100, Math.round(raw)))
  }
  const total = modelLoadingTotalBytes.value
  if (total <= 0) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round((modelLoadingLoadedBytes.value / total) * 100)))
})
const composerStopping = computed(() => chatStore.loading || modelLoadingVisible.value)
const composerActionTitle = computed(() => {
  if (!composerStopping.value) return '发送消息'
  return modelLoadingVisible.value ? '停止模型加载' : '停止生成'
})
const logicFlowLabel = computed(() => {
  if (currentModelFamily.value === 'qwen3') return 'Qwen3 逻辑流程图'
  if (currentModelFamily.value === 'qwen2') return 'Qwen2 逻辑流程图'
  return '当前模型逻辑流程图'
})
const activeTrace = computed(() => chatStore.inferenceTrace || null)
const traceSteps = computed(() => (Array.isArray(activeTrace.value?.steps) ? activeTrace.value.steps : []))
const traceStateText = computed(() => {
  const state = String(activeTrace.value?.state || '').toLowerCase()
  if (state === 'disabled') return '已关闭'
  if (state === 'running') return '运行中'
  if (state === 'completed') return '已完成'
  if (state === 'cancelled') return '已停止'
  if (state === 'error') return '异常'
  return chatStore.loading ? '运行中' : '待机'
})
const traceStateClass = computed(() => {
  const state = String(activeTrace.value?.state || '').toLowerCase()
  if (state === 'disabled') return 'idle'
  if (state === 'running') return 'running'
  if (state === 'completed') return 'completed'
  if (state === 'cancelled') return 'cancelled'
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
  attention: ['attn.wq', 'attn.q_norm', 'attn.wk', 'attn.k_norm', 'attn.wv', 'attn.rope', 'attn.mha', 'attn.wo'],
  wq: ['attn.wq', 'attn.q_norm'],
  wk: ['attn.wk', 'attn.k_norm'],
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

function readThinkPreference() {
  try {
    return localStorage.getItem(THINK_PREFERENCE_KEY) !== '0'
  } catch {
    return true
  }
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

function formatBytes(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) {
    return '0 B'
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = index === 0 || size >= 100 ? 0 : 1
  return `${size.toFixed(digits)} ${units[index]}`
}

function fallbackCopyText(text) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  document.body.removeChild(textarea)
  if (!copied) {
    throw new Error('复制失败')
  }
}

async function handleCopyMessage(message) {
  const text = String(message?.content || '').trim()
  if (!text) {
    ElMessage.warning('没有可复制的内容')
    return
  }
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      fallbackCopyText(text)
    }
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

function canPersistMessageFeedback(message) {
  return Boolean(message?.id && message?.conversation_id && !message?.pending)
}

function isMessageFeedbackActive(message, feedback) {
  return String(message?.feedback || '') === feedback
}

async function handleMessageFeedback(message, feedback) {
  if (!canPersistMessageFeedback(message)) {
    ElMessage.warning('消息保存后才能标记')
    return
  }

  const nextFeedback = isMessageFeedbackActive(message, feedback) ? null : feedback
  try {
    await chatStore.updateMessageFeedback(message.id, nextFeedback)
    if (!nextFeedback) {
      ElMessage.success('已取消标记')
    } else {
      ElMessage.success(nextFeedback === 'like' ? '已点赞' : '已点踩')
    }
  } catch (err) {
    ElMessage.error(err?.detail || '标记失败')
  }
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
  }, 500)
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

watch(
  () => chatStore.inferenceStatus?.current_model_id,
  value => {
    selectedModelId.value = String(value || '')
  },
  { immediate: true }
)

watch(thinkEnabled, value => {
  try {
    localStorage.setItem(THINK_PREFERENCE_KEY, value ? '1' : '0')
  } catch {
    // ignore persistence failures
  }
})

async function handleSelectConversation(id) {
  await chatStore.selectConversation(id)
}

async function handleNewChat() {
  await chatStore.createConversation()
  nextTick(() => inputRef.value?.focus && inputRef.value.focus())
}

async function handleSend() {
  const content = inputMessage.value.trim()
  if (!content || composerStopping.value) return
  inputMessage.value = ''
  await chatStore.sendMessage(content, thinkEnabled.value)
  nextTick(() => inputRef.value?.focus && inputRef.value.focus())
}

async function handleComposerAction() {
  if (composerStopping.value) {
    try {
      await chatStore.cancelGeneration()
    } catch (e) {
      ElMessage.error(formatErrorMessage(e, modelLoadingVisible.value ? '停止模型加载失败' : '停止生成失败'))
    }
    return
  }
  await handleSend()
}

async function handleModelChange(modelId) {
  const nextId = String(modelId || '').trim()
  const currentId = String(chatStore.inferenceStatus?.current_model_id || '').trim()
  if (!nextId || nextId === currentId) {
    return
  }
  try {
    await chatStore.switchInferenceModel(nextId)
    ElMessage.success(`已切换到 ${chatStore.inferenceStatus?.current_model_name || nextId}`)
  } catch (e) {
    selectedModelId.value = currentId
    ElMessage.error(formatErrorMessage(e, '切换模型失败'))
  }
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

async function handleRenameConversation(conversation) {
  try {
    const result = await ElMessageBox.prompt('输入新的对话名称', '重命名', {
      inputValue: conversation?.title || '新对话',
      inputValidator: value => (String(value || '').trim() ? true : '对话名称不能为空'),
      confirmButtonText: '保存',
      cancelButtonText: '取消'
    })
    const title = String(result?.value || '').trim()
    await chatStore.renameConversation(conversation.id, title)
    ElMessage.success('已重命名')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(formatErrorMessage(e, '重命名失败'))
    }
  }
}

function handlePinConversation(conversation) {
  const pinned = chatStore.togglePinConversation(conversation.id)
  ElMessage.success(pinned ? '已置顶' : '已取消置顶')
}

function handleConversationCommand(command, conversation) {
  if (command === 'rename') {
    handleRenameConversation(conversation)
    return
  }
  if (command === 'pin') {
    handlePinConversation(conversation)
    return
  }
  if (command === 'delete') {
    handleDelete(conversation.id)
  }
}

function handleMessageClick(message) {
  if (!message || message.role !== 'assistant') {
    return
  }
  if (message.inference_trace && typeof message.inference_trace === 'object') {
    chatStore.inferenceTrace = message.inference_trace
    if (traceSidebarCollapsed.value) {
      traceSidebarCollapsed.value = false
    }
  }
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.chat-shell {
  --surface-sidebar: #f7f7f8;
  --surface-sidebar-hover: #ececec;
  --surface-main: #ffffff;
  --surface-input: #ffffff;
  --surface-ai-message: #ffffff;
  --surface-user-message: #f4f4f4;
  --border-subtle: #e5e5e5;
  --border-strong: #d8d8d8;
  --text-primary: #171717;
  --text-secondary: #4b5563;
  --text-muted: #8a8f98;
  --accent-color: #111111;
  --accent-color-strong: #000000;
  --danger-color: #c03535;
  --shadow-card: 0 8px 24px rgba(0, 0, 0, 0.08);
  --shadow-float: 0 18px 42px rgba(0, 0, 0, 0.14);
  position: relative;
  display: flex;
  height: 100vh;
  background: #ffffff;
  color: var(--text-primary);
}

.chat-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-right: 1px solid #efefef;
  background: var(--surface-sidebar);
  z-index: 12;
  transition: width 0.22s ease, padding 0.22s ease;
}

.chat-sidebar.collapsed {
  width: 58px;
  padding: 8px 6px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.new-chat-btn {
  flex: 1;
  height: 30px;
  border-radius: 8px;
  border: 0;
  background: #ececec;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 0 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-chat-btn:hover {
  background: #e4e4e4;
}

.new-chat-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-sidebar.collapsed .new-chat-btn {
  flex: unset;
  width: 36px;
  padding: 0;
  justify-content: center;
}

.sidebar-toggle {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.sidebar-toggle:hover {
  background: #ececec;
}

.sidebar-close {
  display: none;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.engine-status {
  height: 30px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 8px;
  font-size: 12px;
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
  background: transparent;
}

.engine-status.online .status-dot {
  background: #10a37f;
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.14);
}

.conversation-section-label {
  padding: 10px 8px 4px;
  color: #9b9b9b;
  font-size: 12px;
}

.conversation-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-right: 0;
}

.conversation-item {
  width: 100%;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 7px 8px;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease;
  outline: none;
}

.chat-sidebar.collapsed .conversation-item {
  justify-content: center;
  padding: 10px 0;
}

.conversation-item:hover {
  background: var(--surface-sidebar-hover);
}

.conversation-item.active {
  background: #ececec;
}

.conversation-item:focus-visible {
  box-shadow: 0 0 0 2px rgba(17, 17, 17, 0.16);
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

.conversation-title-row {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.conv-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pin-mark {
  flex-shrink: 0;
  border: 0;
  border-radius: 6px;
  background: #e6f5ef;
  color: #0f766e;
  padding: 0 5px;
  font-size: 11px;
  line-height: 16px;
}

.conv-time {
  display: none;
  color: var(--text-muted);
  font-size: 12px;
}

.conversation-menu {
  flex-shrink: 0;
}

.conversation-menu-btn {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #6b7280;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  opacity: 0;
  cursor: pointer;
  transition: opacity 0.2s ease, background 0.2s ease;
}

.conversation-menu-btn span {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentColor;
}

.conversation-item:hover .conversation-menu-btn,
.conversation-item:focus-within .conversation-menu-btn,
.conversation-item.active .conversation-menu-btn {
  opacity: 1;
}

.conversation-menu-btn:hover {
  background: #dedede;
}

.user-panel {
  border: 0;
  border-radius: 8px;
  background: transparent;
  padding: 6px;
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
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #10a37f;
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
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  color: var(--text-secondary);
  background: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.logout-btn:hover {
  background: #ececec;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  background: #ffffff;
}

.chat-header {
  min-height: 52px;
  border-bottom: 0;
  background: #ffffff;
  padding: 8px 28px 6px;
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
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.model-switcher {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.model-switcher-label {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.model-switcher-select {
  width: 210px;
}

.model-switcher-select :deep(.el-select__wrapper) {
  min-height: 30px;
  border-radius: 8px;
  background: #f7f7f8;
  box-shadow: none;
}

.model-switcher-select :deep(.el-select__placeholder),
.model-switcher-select :deep(.el-select__selected-item) {
  font-size: 13px;
}

.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.model-option-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.think-toggle {
  height: 30px;
  border-radius: 8px;
  border: 0;
  background: #f7f7f8;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.think-toggle-label {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.think-toggle :deep(.el-switch) {
  --el-switch-on-color: #111111;
  --el-switch-off-color: #c8d1df;
}

.header-meta h1 {
  font-size: 15px;
  color: var(--text-primary);
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.current-model-line {
  margin-top: 3px;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 12px;
}

.current-model-name {
  min-width: 0;
  max-width: 240px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.model-loading-inline {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.model-loading-inline-bar {
  width: 150px;
  flex-shrink: 0;
}

.model-loading-inline-text {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.model-loading-inline :deep(.el-progress-bar__outer) {
  background-color: #eeeeee;
}

.model-loading-inline :deep(.el-progress-bar__inner) {
  background-color: #111111;
}

.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 0 16px;
}

.message-track {
  width: min(820px, calc(100% - 44px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.welcome-card {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  padding: 0;
  text-align: center;
}

.welcome-card h2 {
  font-size: 34px;
  line-height: 1.2;
  color: #171717;
  font-weight: 650;
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

.message-row.clickable {
  cursor: pointer;
}

.message-row.clickable .assistant-avatar,
.message-row.clickable .message-body.assistant {
  transition: box-shadow 0.22s ease, transform 0.18s ease, border-color 0.22s ease, background 0.22s ease;
}

.message-row.clickable:hover .assistant-avatar {
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12);
  transform: translateY(-1px);
}

.message-row.clickable:hover .message-body.assistant {
  background: #fafafa;
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.assistant-avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: #10a37f;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.message-stack {
  position: relative;
  max-width: min(84%, 780px);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.message-row.user .message-stack {
  align-items: flex-end;
}

.message-body {
  position: relative;
  max-width: 100%;
  border-radius: 12px;
  padding: 12px 14px;
  line-height: 1.75;
  font-size: 15px;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-content {
  min-width: 0;
}

.message-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  margin-top: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.14s ease, visibility 0.14s ease;
}

.message-row.user .message-actions {
  justify-content: flex-end;
}

.message-stack:hover .message-actions,
.message-stack:focus-within .message-actions,
.message-actions:hover {
  opacity: 1;
  visibility: visible;
}

.message-action-btn {
  position: relative;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #6f6f6f;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.14s ease, color 0.14s ease;
}

.message-action-btn svg {
  width: 19px;
  height: 19px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.message-action-btn:hover {
  color: #111;
  background: #eeeeee;
}

.message-action-btn.active {
  color: #111;
  background: #e9e9e9;
}

.message-action-btn::after {
  content: attr(data-tooltip);
  position: absolute;
  top: calc(100% + 7px);
  left: 50%;
  z-index: 20;
  transform: translateX(-50%) translateY(-2px);
  padding: 5px 8px;
  border-radius: 6px;
  background: #0b0b0b;
  color: #fff;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.message-action-btn:hover::after,
.message-action-btn:focus-visible::after {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.message-body.assistant {
  background: var(--surface-ai-message);
  border: 0;
  color: var(--text-primary);
}

.message-body.assistant.thinking {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-body.user {
  background: var(--surface-user-message);
  border: 0;
  color: #171717;
}

.assistant-think-panel {
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  background: #fafafa;
  overflow: hidden;
}

.assistant-think-panel summary {
  cursor: pointer;
  list-style: none;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  background: #f2f2f2;
}

.assistant-think-panel summary::-webkit-details-marker {
  display: none;
}

.assistant-think-text {
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  color: #4b5563;
}

.assistant-answer-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.message-body.loading {
  min-width: 64px;
  padding: 12px 14px;
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
  border-top: 0;
  background: #ffffff;
}

.composer-box {
  width: min(700px, calc(100% - 44px));
  margin: 0 auto;
  border: 1px solid #d9d9d9;
  border-radius: 28px;
  background: var(--surface-input);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 58px;
  padding: 10px 12px 10px 14px;
}

.composer-plus-btn {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #5f6368;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
}

.composer-plus-btn:hover {
  background: #f1f1f1;
}

.composer-box :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  color: var(--text-primary);
  min-height: 30px !important;
  font-size: 18px;
  line-height: 30px;
  padding: 0;
}

.composer-box :deep(.el-textarea__inner::placeholder) {
  color: #8e8e8e;
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: #111111;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  transition: background 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  background: #000000;
}

.send-btn.stopping {
  background: #1f2937;
}

.send-btn.stopping:hover:not(:disabled) {
  background: #111827;
  transform: scale(0.98);
}

.send-btn.busy {
  opacity: 0.72;
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.send-btn-stop-square {
  width: 11px;
  height: 11px;
  border-radius: 3px;
  background: currentColor;
}

.composer-note {
  width: min(700px, calc(100% - 44px));
  margin: 8px auto 0;
  color: var(--text-muted);
  text-align: center;
  font-size: 12px;
}

.chat-main.empty-chat .message-list {
  position: relative;
  display: block;
  padding: 0;
}

.chat-main.empty-chat .message-track {
  position: absolute;
  left: 50%;
  top: 33%;
  width: min(700px, calc(100% - 72px));
  min-height: 0;
  display: block;
  padding: 0;
  transform: translateX(-50%);
}

.chat-main.empty-chat .welcome-card p {
  display: none;
}

.chat-main.empty-chat .composer-area {
  position: absolute;
  left: 50%;
  top: calc(33% + 128px);
  z-index: 5;
  width: min(700px, calc(100% - 72px));
  padding: 0;
  transform: translateX(-50%);
  background: transparent;
}

.chat-main.empty-chat .composer-box {
  width: 100%;
}

.chat-main.empty-chat .composer-note {
  display: none;
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
  width: 0;
  border-left: 0;
  overflow: hidden;
}

.trace-sidebar.collapsed .trace-sidebar-header,
.trace-sidebar.collapsed .trace-sidebar-body,
.trace-sidebar.collapsed .trace-resize-handle {
  display: none;
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

.trace-state-value.cancelled {
  color: #c2410c;
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

.trace-scrollbox {
  max-height: 200px;
  overflow: auto;
}

.trace-scrollbox--tokens {
  max-height: 200px;
}

.trace-scrollbox--text {
  max-height: 220px;
}

.trace-scrollbox--box {
  padding: 7px 8px;
  border-radius: 8px;
  background: #f4f7fd;
  border: 1px solid #e1e7f2;
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
    padding: 10px 14px;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .current-model-line {
    flex-wrap: wrap;
  }

  .model-loading-inline {
    flex-wrap: wrap;
  }

  .model-loading-inline-bar {
    width: 120px;
  }

  .message-track,
  .composer-box,
  .composer-note {
    width: calc(100% - 20px);
  }

  .chat-main.empty-chat .composer-area {
    width: calc(100% - 28px);
  }

  .message-body {
    max-width: 100%;
  }

  .trace-sidebar {
    display: none;
  }
}
</style>

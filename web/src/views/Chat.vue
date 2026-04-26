<template>
  <div class="chat-shell">
    <aside class="chat-sidebar" :class="{ show: mobileSidebarOpen, collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <button class="new-chat-btn" :disabled="chatStore.creatingConversation" @click="handleNewChat">
          <el-icon><Plus /></el-icon>
          <span v-if="!sidebarCollapsed">新对话</span>
        </button>
        <button class="sidebar-toggle" :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleSidebar">
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
            <span v-if="currentModelSeqLenText" class="current-model-context">
              上下文 {{ currentModelSeqLenText }}
            </span>
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
                    {{ model.family || 'model' }}{{ formatModelSeqLen(model.seq_len) }}{{ model.ready ? '' : ' · 未就绪' }}
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
            :class="[msg.role]"
          >
            <div v-if="msg.role !== 'user'" class="assistant-avatar">
              <el-icon><Monitor /></el-icon>
            </div>
            <div class="message-stack">
              <div class="message-body" :class="[msg.role, { thinking: msg.role === 'assistant' && !!msg.reasoning_content && thinkEnabled }]">
                <div class="message-content">
                  <template v-if="msg.role === 'assistant' && msg.pending && !msg.content && (!msg.reasoning_content || !thinkEnabled)">
                    <div class="message-loading-inline">
                      <span></span><span></span><span></span>
                    </div>
                  </template>
                  <template v-else-if="msg.role === 'assistant' && msg.reasoning_content && thinkEnabled">
                    <details class="assistant-think-panel">
                      <summary>思考过程</summary>
                      <div class="assistant-think-text markdown-content" v-html="renderMarkdown(msg.reasoning_content)"></div>
                    </details>
                    <div class="assistant-answer-text markdown-content" v-html="renderMarkdown(msg.content)"></div>
                  </template>
                  <template v-else>
                    <div class="markdown-content" v-html="renderMarkdown(msg.content)"></div>
                  </template>
                </div>
              </div>
              <div v-if="!msg.pending" class="message-actions" @click.stop>
                <button
                  v-if="hasMessageTrace(msg)"
                  class="message-action-btn"
                  :class="{ active: isMessageTraceActive(msg) }"
                  type="button"
                  aria-label="查看埋点"
                  data-tooltip="埋点"
                  @click.stop="openMessageTrace(msg)"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3 12h3l2.2-4.5 3.6 9 2.4-5h5.8"></path>
                    <circle cx="18" cy="7" r="2"></circle>
                  </svg>
                </button>
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
            v-if="chatStore.loading && chatStore.currentConversation?.id === chatStore.loadingConversationId && !chatStore.loadingReplyReady"
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
        <button class="trace-sidebar-toggle" :title="traceSidebarCollapsed ? '展开埋点面板' : '收起埋点面板'" @click="toggleTraceSidebar">
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
import { ChatDotRound, CloseBold, Expand, Fold, Monitor, Plus, Promotion, SwitchButton } from '@element-plus/icons-vue'

import { useChatView } from './chat/useChatView'

const {
  activeTrace,
  authStore,
  availableModels,
  chatStore,
  composerActionTitle,
  composerStopping,
  currentModelName,
  currentModelSeqLenText,
  engineTraceEnabled,
  formatConversationTime,
  formatDuration,
  formatModelSeqLen,
  formatTokenIds,
  handleComposerAction,
  handleConversationCommand,
  handleCopyMessage,
  handleLogout,
  handleMessageFeedback,
  handleModelChange,
  handleNewChat,
  handleSend,
  handleSelectConversation,
  hasMessageTrace,
  inputMessage,
  inputRef,
  isMessageFeedbackActive,
  isMessageTraceActive,
  logicFlowLabel,
  logicalNodeDuration,
  messageListRef,
  mobileSidebarOpen,
  openMessageTrace,
  renderMarkdown,
  selectedModelId,
  sidebarCollapsed,
  startTraceResize,
  thinkEnabled,
  toggleSidebar,
  toggleTraceSidebar,
  traceSidebarCollapsed,
  traceSidebarStyle,
  traceStateClass,
  traceStateText,
  traceSteps
} = useChatView()
</script>

<style scoped src="./chat/chat-view.css"></style>

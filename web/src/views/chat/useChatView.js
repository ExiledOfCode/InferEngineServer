import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'
import { renderMarkdown } from '../../utils/markdown'

const THINK_PREFERENCE_KEY = 'chat:show-think'
const TRACE_SIDEBAR_MIN_WIDTH = 360
const TRACE_SIDEBAR_MAX_WIDTH = 860

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

function formatModelSeqLen(value) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return ''
  }
  return ` · ${Math.round(numeric).toLocaleString()} tokens`
}

export function useChatView() {
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
  const traceResizing = ref(false)
  const traceResizeStartX = ref(0)
  const traceResizeStartWidth = ref(460)
  const selectedModelId = ref('')
  const thinkEnabled = ref(readThinkPreference())

  let statusTimer = null

  const availableModels = computed(() => (
    Array.isArray(chatStore.inferenceStatus?.available_models) ? chatStore.inferenceStatus.available_models : []
  ))
  const currentModelName = computed(() => chatStore.inferenceStatus?.current_model_name || '')
  const currentModelFamily = computed(() => String(chatStore.inferenceStatus?.current_model_family || '').toLowerCase())
  const currentModelSupportsReasoning = computed(() => chatStore.inferenceStatus?.current_model_supports_reasoning === true)
  const currentModelSeqLen = computed(() => Number(chatStore.inferenceStatus?.current_model_seq_len || 0))
  const currentModelSeqLenText = computed(() => formatModelSeqLen(currentModelSeqLen.value).replace(/^ · /, ''))
  const engineTraceEnabled = computed(() => chatStore.inferenceStatus?.trace_enabled === true)
  const modelLoadingVisible = computed(() => {
    const state = String(chatStore.inferenceStatus?.model_loading_progress?.state || '').toLowerCase()
    return ['starting', 'loading'].includes(state)
  })
  const composerStopping = computed(() => chatStore.loading || modelLoadingVisible.value)
  const composerActionTitle = computed(() => (
    modelLoadingVisible.value ? '停止模型加载' : composerStopping.value ? '停止生成' : '发送消息'
  ))
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
  const traceSidebarStyle = computed(() => (
    traceSidebarCollapsed.value ? undefined : { width: `${traceSidebarWidth.value}px` }
  ))

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

  function hasMessageTrace(message) {
    return Boolean(message?.role === 'assistant' && message?.inference_trace && typeof message.inference_trace === 'object')
  }

  function isMessageTraceActive(message) {
    if (!hasMessageTrace(message) || !activeTrace.value || typeof activeTrace.value !== 'object') {
      return false
    }
    const currentRequestId = activeTrace.value?.request_id
    const messageRequestId = message.inference_trace?.request_id
    if (currentRequestId !== undefined && currentRequestId !== null && messageRequestId !== undefined && messageRequestId !== null) {
      return String(currentRequestId) === String(messageRequestId)
    }
    return activeTrace.value === message.inference_trace
  }

  function openMessageTrace(message) {
    if (!hasMessageTrace(message)) {
      return
    }
    chatStore.inferenceTrace = message.inference_trace
    if (traceSidebarCollapsed.value) {
      traceSidebarCollapsed.value = false
    }
  }

  async function handleMessageFeedback(message, feedback) {
    if (!canPersistMessageFeedback(message)) {
      ElMessage.warning('消息保存后才能标记')
      return
    }

    const nextFeedback = isMessageFeedbackActive(message, feedback) ? null : feedback
    try {
      await chatStore.updateMessageFeedback(message.id, nextFeedback)
      ElMessage.success(nextFeedback ? (nextFeedback === 'like' ? '已点赞' : '已点踩') : '已取消标记')
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
    traceSidebarWidth.value = Math.max(TRACE_SIDEBAR_MIN_WIDTH, Math.min(TRACE_SIDEBAR_MAX_WIDTH, next))
  }

  function stopTraceResize() {
    if (!traceResizing.value) return
    traceResizing.value = false
    document.body.style.userSelect = ''
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
    await chatStore.sendMessage(content, currentModelSupportsReasoning.value && thinkEnabled.value)
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

  function handleLogout() {
    authStore.logout()
    router.push('/login')
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
    () => chatStore.messages.map(message => (
      `${message.id}:${message.pending ? 1 : 0}:${(message.content || '').length}:${(message.reasoning_content || '').length}`
    )).join('|'),
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

  return {
    activeTrace,
    authStore,
    availableModels,
    chatStore,
    composerActionTitle,
    composerStopping,
    currentModelName,
    currentModelSupportsReasoning,
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
    modelLoadingVisible,
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
  }
}

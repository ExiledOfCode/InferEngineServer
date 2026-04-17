import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '../api'
import { ElMessage } from 'element-plus'

const CHAT_STATUS_POLL_INTERVAL_MS = 500
const PINNED_CONVERSATIONS_KEY = 'chat:pinned-conversations'

function collapseRepeatedLines(content) {
  const lines = String(content || '').split('\n')
  if (lines.length <= 1) {
    return String(content || '')
  }

  const kept = []
  let prevNorm = ''
  let sameRun = 0

  for (const line of lines) {
    const norm = line.trim()
    if (norm && norm === prevNorm && norm.length <= 48) {
      sameRun += 1
      if (sameRun >= 2 && norm.length <= 32) {
        if (kept.length > 0 && kept[kept.length - 1].trim() === norm) {
          kept.pop()
        }
        break
      }
      if (sameRun >= 3) {
        continue
      }
    } else {
      prevNorm = norm
      sameRun = 1
    }
    kept.push(line)
  }
  return kept.join('\n').trim()
}

function sanitizeAssistantContent(content) {
  return collapseRepeatedLines(String(content || '').trim())
}

function formatApiError(err) {
  const detail = err?.detail || err?.message || '发送失败'
  const status = err?.status ? `HTTP ${err.status}` : ''
  const method = err?.method ? String(err.method).toUpperCase() : ''
  const baseURL = err?.baseURL || ''
  const path = err?.url || ''
  const requestLine = method || baseURL || path ? `${method} ${baseURL}${path}`.trim() : ''
  return [detail, status, requestLine].filter(Boolean).join(' | ')
}

function isInferenceCancelledError(err) {
  const detail = String(err?.detail || err?.message || '').toLowerCase()
  return err?.status === 409 && (detail.includes('取消') || detail.includes('cancel'))
}

function normalizeAssistantMessage(payload) {
  if (payload && typeof payload === 'object' && typeof payload.content === 'string') {
    const normalized = { ...payload, content: sanitizeAssistantContent(payload.content) }
    if (typeof payload.reasoning_content === 'string') {
      normalized.reasoning_content = sanitizeAssistantContent(payload.reasoning_content)
    }
    if (typeof payload.raw_content === 'string') {
      normalized.raw_content = sanitizeAssistantContent(payload.raw_content)
    }
    return normalized
  }
  if (typeof payload === 'string') {
    return {
      id: Date.now() + 1,
      role: 'assistant',
      content: sanitizeAssistantContent(payload),
      created_at: new Date().toISOString()
    }
  }
  return {
    id: Date.now() + 1,
    role: 'assistant',
    content: sanitizeAssistantContent(`推理返回格式异常: ${JSON.stringify(payload)}`),
    created_at: new Date().toISOString()
  }
}

function normalizeMessages(messages) {
  if (!Array.isArray(messages)) {
    return []
  }
  return messages.map(msg => {
    if (msg?.role === 'assistant' && typeof msg?.content === 'string') {
      const normalized = { ...msg, content: sanitizeAssistantContent(msg.content) }
      if (typeof msg?.reasoning_content === 'string') {
        normalized.reasoning_content = sanitizeAssistantContent(msg.reasoning_content)
      }
      if (typeof msg?.raw_content === 'string') {
        normalized.raw_content = sanitizeAssistantContent(msg.raw_content)
      }
      return normalized
    }
    return msg
  })
}

function normalizeFeedback(value) {
  return value === 'like' || value === 'dislike' ? value : null
}

function pickLatestStoredTrace(messages) {
  if (!Array.isArray(messages)) return null
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const item = messages[i]
    if (item?.role === 'assistant' && item?.inference_trace && typeof item.inference_trace === 'object') {
      return item.inference_trace
    }
  }
  return null
}

function readPinnedConversationIds() {
  try {
    const raw = localStorage.getItem(PINNED_CONVERSATIONS_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.map(id => String(id)).filter(Boolean) : []
  } catch {
    return []
  }
}

function persistPinnedConversationIds(ids) {
  try {
    localStorage.setItem(PINNED_CONVERSATIONS_KEY, JSON.stringify(ids))
  } catch {
    // ignore persistence failures
  }
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const pinnedConversationIds = ref(readPinnedConversationIds())
  const currentConversation = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const canceling = ref(false)
  const loadingConversationId = ref(null)
  const creatingConversation = ref(false)
  const switchingModel = ref(false)
  const inferenceStatus = ref(null)
  const inferenceTrace = ref(null)

  function isTraceEnabled() {
    return inferenceStatus.value?.trace_enabled !== false
  }

  function isModelLoadingStatus() {
    const state = String(inferenceStatus.value?.model_loading_progress?.state || '').toLowerCase()
    return state === 'starting' || state === 'loading'
  }

  function isConversationPinned(id) {
    return pinnedConversationIds.value.includes(String(id))
  }

  function orderConversations(items) {
    const pinnedIndex = new Map(pinnedConversationIds.value.map((id, index) => [String(id), index]))
    return [...(Array.isArray(items) ? items : [])].sort((a, b) => {
      const aPinned = pinnedIndex.has(String(a?.id))
      const bPinned = pinnedIndex.has(String(b?.id))
      if (aPinned && bPinned) {
        return pinnedIndex.get(String(a.id)) - pinnedIndex.get(String(b.id))
      }
      if (aPinned) return -1
      if (bPinned) return 1
      return 0
    })
  }

  function setConversations(items) {
    const existingIds = new Set((Array.isArray(items) ? items : []).map(item => String(item?.id)))
    const nextPinned = pinnedConversationIds.value.filter(id => existingIds.has(String(id)))
    if (nextPinned.length !== pinnedConversationIds.value.length) {
      pinnedConversationIds.value = nextPinned
      persistPinnedConversationIds(nextPinned)
    }
    conversations.value = orderConversations(items)
  }

  async function fetchConversations() {
    setConversations(await chatApi.getConversations())
  }

  async function createConversation() {
    if (creatingConversation.value) {
      return currentConversation.value
    }

    // 已在空白会话中，重复点击不再新建
    if (currentConversation.value && messages.value.length === 0) {
      return currentConversation.value
    }

    // 已存在空会话时直接切换，避免重复空会话
    const existingEmpty = conversations.value.find(conv => (conv?.title || '') === '新对话')
    if (existingEmpty) {
      await selectConversation(existingEmpty.id)
      return existingEmpty
    }

    creatingConversation.value = true
    try {
      const conv = await chatApi.createConversation({ title: '新对话' })
      conversations.value = orderConversations([conv, ...conversations.value])
      await selectConversation(conv.id)
      return conv
    } finally {
      creatingConversation.value = false
    }
  }

  async function deleteConversation(id) {
    await chatApi.deleteConversation(id)
    pinnedConversationIds.value = pinnedConversationIds.value.filter(item => item !== String(id))
    persistPinnedConversationIds(pinnedConversationIds.value)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConversation.value?.id === id) {
      currentConversation.value = null
      messages.value = []
      inferenceTrace.value = null
    }
  }

  async function renameConversation(id, title) {
    const nextTitle = String(title || '').trim()
    if (!nextTitle) {
      return null
    }

    const updated = await chatApi.updateConversation(id, { title: nextTitle })
    conversations.value = orderConversations(
      conversations.value.map(conv => (conv.id === id ? { ...conv, ...updated } : conv))
    )
    if (currentConversation.value?.id === id) {
      currentConversation.value = { ...currentConversation.value, ...updated }
    }
    return updated
  }

  function togglePinConversation(id) {
    const key = String(id)
    if (!key) {
      return false
    }
    const next = pinnedConversationIds.value.filter(item => item !== key)
    const shouldPin = next.length === pinnedConversationIds.value.length
    if (shouldPin) {
      next.unshift(key)
    }
    pinnedConversationIds.value = next
    persistPinnedConversationIds(next)
    conversations.value = orderConversations(conversations.value)
    return shouldPin
  }

  async function selectConversation(id) {
    currentConversation.value = conversations.value.find(c => c.id === id) || null
    if (currentConversation.value) {
      const loaded = normalizeMessages(await chatApi.getMessages(id))
      messages.value = loaded
      const storedTrace = pickLatestStoredTrace(loaded)
      if (storedTrace) {
        inferenceTrace.value = storedTrace
      } else if (!isTraceEnabled()) {
        inferenceTrace.value = {
          state: 'disabled',
          enabled: false,
          steps: []
        }
      } else {
        inferenceTrace.value = null
      }
    }
  }

  async function fetchInferenceStatus() {
    inferenceStatus.value = await chatApi.getInferenceStatus()
    if (!isTraceEnabled()) {
      inferenceTrace.value = {
        state: 'disabled',
        enabled: false,
        steps: []
      }
    }
    return inferenceStatus.value
  }

  async function fetchInferenceTrace() {
    if (!isTraceEnabled()) {
      inferenceTrace.value = {
        state: 'disabled',
        enabled: false,
        steps: []
      }
      return inferenceTrace.value
    }
    inferenceTrace.value = await chatApi.getInferenceTrace()
    return inferenceTrace.value
  }

  async function switchInferenceModel(modelId) {
    const nextId = String(modelId || '').trim()
    if (!nextId || switchingModel.value) {
      return inferenceStatus.value
    }
    switchingModel.value = true
    try {
      inferenceStatus.value = await chatApi.selectInferenceModel(nextId)
      inferenceTrace.value = isTraceEnabled()
        ? null
        : {
            state: 'disabled',
            enabled: false,
            steps: []
          }
      return inferenceStatus.value
    } finally {
      switchingModel.value = false
    }
  }

  async function cancelGeneration() {
    if ((!loading.value && !isModelLoadingStatus()) || canceling.value) {
      return false
    }

    canceling.value = true
    try {
      await chatApi.cancelInference()
      if (inferenceTrace.value && typeof inferenceTrace.value === 'object') {
        inferenceTrace.value = {
          ...inferenceTrace.value,
          cancel_requested: true
        }
      }
      return true
    } catch (err) {
      if (err?.status === 409) {
        return false
      }
      throw err
    } finally {
      canceling.value = false
    }
  }

  async function updateMessageFeedback(messageId, feedback) {
    const nextFeedback = normalizeFeedback(feedback)
    const updated = await chatApi.updateMessageFeedback(messageId, nextFeedback)
    messages.value = messages.value.map(message => (
      message.id === messageId
        ? { ...message, feedback: normalizeFeedback(updated?.feedback) }
        : message
    ))
    return updated
  }

  async function sendMessage(content, thinkEnabled = true) {
    if (!currentConversation.value) {
      await createConversation()
    }

    const convId = currentConversation.value.id
    const tempUserMessage = {
      id: Date.now(),
      conversation_id: convId,
      role: 'user',
      content,
      pending: true,
      created_at: new Date().toISOString()
    }
    messages.value.push(tempUserMessage)
    loading.value = true
    loadingConversationId.value = convId
    let traceTimer = null
    let statusTimer = null
    const pollTrace = async () => {
      try {
        await fetchInferenceTrace()
      } catch {
        // ignore trace polling errors
      }
    }
    const pollStatus = async () => {
      try {
        await fetchInferenceStatus()
      } catch {
        // ignore status polling errors
      }
    }
    await pollStatus()
    statusTimer = window.setInterval(pollStatus, CHAT_STATUS_POLL_INTERVAL_MS)
    if (isTraceEnabled()) {
      await pollTrace()
      traceTimer = window.setInterval(pollTrace, 700)
    } else {
      inferenceTrace.value = {
        state: 'disabled',
        enabled: false,
        steps: []
      }
    }

    try {
      const response = normalizeAssistantMessage(await chatApi.sendMessage(convId, content, thinkEnabled))
      if (response?.inference_trace) {
        inferenceTrace.value = response.inference_trace
      } else if (!isTraceEnabled()) {
        inferenceTrace.value = {
          state: 'disabled',
          enabled: false,
          steps: []
        }
      }
      // 优先以后端数据库为准回拉，避免前后端状态漂移
      try {
        messages.value = normalizeMessages(await chatApi.getMessages(convId))
      } catch {
        messages.value.push(response)
      }
      if (messages.value.length <= 2) {
        currentConversation.value.title = content.slice(0, 50)
      }
    } catch (err) {
      if (isInferenceCancelledError(err)) {
        try {
          messages.value = normalizeMessages(await chatApi.getMessages(convId))
        } catch {
          // ignore refresh error after cancel
        }
        if (currentConversation.value && (!currentConversation.value.title || currentConversation.value.title === '新对话')) {
          currentConversation.value.title = content.slice(0, 50)
        }
        return
      }
      try {
        messages.value = normalizeMessages(await chatApi.getMessages(convId))
      } catch {
        // ignore secondary error
      }
      const detail = formatApiError(err)
      messages.value.push({
        id: Date.now() + 1,
        role: 'assistant',
        content: `推理失败: ${sanitizeAssistantContent(detail)}`,
        created_at: new Date().toISOString()
      })
      ElMessage.error(detail)
    } finally {
      if (traceTimer) {
        window.clearInterval(traceTimer)
        traceTimer = null
      }
      if (statusTimer) {
        window.clearInterval(statusTimer)
        statusTimer = null
      }
      if (isTraceEnabled()) {
        try {
          await fetchInferenceTrace()
        } catch {
          // ignore final trace refresh
        }
      } else {
        inferenceTrace.value = {
          state: 'disabled',
          enabled: false,
          steps: []
        }
      }
      try {
        await fetchInferenceStatus()
      } catch {
        // ignore status refresh failure
      }
      loading.value = false
      loadingConversationId.value = null
    }
  }

  return {
    conversations,
    pinnedConversationIds,
    currentConversation,
    messages,
    loading,
    canceling,
    loadingConversationId,
    creatingConversation,
    switchingModel,
    inferenceStatus,
    inferenceTrace,
    fetchConversations,
    createConversation,
    deleteConversation,
    renameConversation,
    togglePinConversation,
    isConversationPinned,
    selectConversation,
    fetchInferenceStatus,
    fetchInferenceTrace,
    switchInferenceModel,
    cancelGeneration,
    updateMessageFeedback,
    sendMessage
  }
})

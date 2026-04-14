import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '../api'
import { ElMessage } from 'element-plus'

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

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
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

  async function fetchConversations() {
    conversations.value = await chatApi.getConversations()
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
      conversations.value.unshift(conv)
      await selectConversation(conv.id)
      return conv
    } finally {
      creatingConversation.value = false
    }
  }

  async function deleteConversation(id) {
    await chatApi.deleteConversation(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConversation.value?.id === id) {
      currentConversation.value = null
      messages.value = []
    }
  }

  async function selectConversation(id) {
    currentConversation.value = conversations.value.find(c => c.id === id) || null
    if (currentConversation.value) {
      messages.value = normalizeMessages(await chatApi.getMessages(id))
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
    if (!loading.value || canceling.value) {
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

  async function sendMessage(content) {
    if (!currentConversation.value) {
      await createConversation()
    }

    const convId = currentConversation.value.id
    const tempUserMessage = {
      id: Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString()
    }
    messages.value.push(tempUserMessage)
    loading.value = true
    loadingConversationId.value = convId
    let traceTimer = null
    const pollTrace = async () => {
      try {
        await fetchInferenceTrace()
      } catch {
        // ignore trace polling errors
      }
    }
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
      const response = normalizeAssistantMessage(await chatApi.sendMessage(convId, content))
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
    selectConversation,
    fetchInferenceStatus,
    fetchInferenceTrace,
    switchInferenceModel,
    cancelGeneration,
    sendMessage
  }
})

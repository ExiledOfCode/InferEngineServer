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

function normalizeAssistantMessage(payload) {
  if (payload && typeof payload === 'object' && typeof payload.content === 'string') {
    return { ...payload, content: sanitizeAssistantContent(payload.content) }
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
      return { ...msg, content: sanitizeAssistantContent(msg.content) }
    }
    return msg
  })
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const currentConversation = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const inferenceStatus = ref(null)

  async function fetchConversations() {
    conversations.value = await chatApi.getConversations()
  }

  async function createConversation() {
    const conv = await chatApi.createConversation({ title: '新对话' })
    conversations.value.unshift(conv)
    await selectConversation(conv.id)
    return conv
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
    return inferenceStatus.value
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

    try {
      const response = normalizeAssistantMessage(await chatApi.sendMessage(convId, content))
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
      loading.value = false
    }
  }

  return {
    conversations,
    currentConversation,
    messages,
    loading,
    inferenceStatus,
    fetchConversations,
    createConversation,
    deleteConversation,
    selectConversation,
    fetchInferenceStatus,
    sendMessage
  }
})

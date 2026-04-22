import api, { getActiveBaseURL } from '../http'
import router from '../../router'
import { useAuthStore } from '../../stores/auth'

function buildStreamPath(id) {
  return `/conversations/${id}/messages/stream`
}

function buildStreamUrl(id) {
  return `${getActiveBaseURL()}${buildStreamPath(id)}`
}

function buildStreamError(detail, status, id) {
  return {
    detail,
    status,
    url: buildStreamPath(id),
    method: 'post',
    baseURL: getActiveBaseURL()
  }
}

async function parseErrorResponse(response) {
  const contentType = String(response.headers.get('content-type') || '').toLowerCase()
  try {
    if (contentType.includes('application/json')) {
      const payload = await response.json()
      return payload?.detail || JSON.stringify(payload)
    }
    const text = await response.text()
    return text || response.statusText || '请求失败'
  } catch {
    return response.statusText || '请求失败'
  }
}

function parseSseBlock(block) {
  const raw = String(block || '').trim()
  if (!raw) {
    return null
  }

  let event = 'message'
  const dataLines = []
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (dataLines.length === 0) {
    return { event, payload: null }
  }

  const payloadText = dataLines.join('\n')
  try {
    return { event, payload: JSON.parse(payloadText) }
  } catch {
    return { event, payload: payloadText }
  }
}

async function consumeEventStream(stream, id, handlers = {}) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let donePayload = null

  const handleEvent = parsed => {
    if (!parsed) {
      return
    }

    const { event, payload } = parsed
    if (event === 'delta') {
      handlers.onDelta?.(payload)
      return
    }
    if (event === 'done') {
      donePayload = payload
      handlers.onDone?.(payload)
      return
    }
    if (event === 'cancelled') {
      handlers.onCancelled?.(payload)
      throw buildStreamError(payload?.detail || '推理已取消', 409, id)
    }
    if (event === 'error') {
      handlers.onError?.(payload)
      throw buildStreamError(payload?.detail || '流式推理失败', 500, id)
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')

    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex)
      buffer = buffer.slice(separatorIndex + 2)
      handleEvent(parseSseBlock(block))
      separatorIndex = buffer.indexOf('\n\n')
    }

    if (done) {
      break
    }
  }

  if (buffer.trim()) {
    handleEvent(parseSseBlock(buffer))
  }

  return donePayload
}

export const chatApi = {
  getConversations: () => api.get('/conversations'),
  createConversation: (data = {}) => api.post('/conversations', data),
  updateConversation: (id, data = {}) => api.put(`/conversations/${id}`, data),
  deleteConversation: id => api.delete(`/conversations/${id}`),
  getMessages: id => api.get(`/conversations/${id}/messages`),
  sendMessage: (id, content, thinkEnabled = true) => api.post(
    `/conversations/${id}/messages`,
    { content, think_enabled: thinkEnabled }
  ),
  async streamMessage(id, content, thinkEnabled = true, handlers = {}) {
    const authStore = useAuthStore()
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    }
    if (authStore.token) {
      headers.Authorization = `Bearer ${authStore.token}`
    }

    const response = await fetch(buildStreamUrl(id), {
      method: 'POST',
      headers,
      body: JSON.stringify({
        content,
        think_enabled: thinkEnabled
      })
    })

    if (response.status === 401) {
      authStore.logout()
      router.push('/login')
      throw buildStreamError('登录已过期', 401, id)
    }

    if (!response.ok) {
      const detail = await parseErrorResponse(response)
      throw buildStreamError(detail, response.status, id)
    }

    if (!response.body) {
      throw buildStreamError('浏览器不支持流式响应', 500, id)
    }

    return consumeEventStream(response.body, id, handlers)
  },
  updateMessageFeedback: (messageId, feedback) => api.put(
    `/messages/${messageId}/feedback`,
    { feedback }
  ),
  cancelInference: () => api.post('/inference/cancel'),
  getInferenceStatus: () => api.get('/inference/status'),
  getInferenceTrace: () => api.get('/inference/trace'),
  getInferenceModels: () => api.get('/inference/models'),
  selectInferenceModel: modelId => api.post('/inference/model/select', { model_id: modelId })
}

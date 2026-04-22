const PINNED_CONVERSATIONS_KEY = 'chat:pinned-conversations'

export function collapseRepeatedLines(content) {
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

export function sanitizeAssistantContent(content) {
  return collapseRepeatedLines(String(content || '').trim())
}

export function formatApiError(err) {
  const detail = err?.detail || err?.message || '发送失败'
  const status = err?.status ? `HTTP ${err.status}` : ''
  const method = err?.method ? String(err.method).toUpperCase() : ''
  const baseURL = err?.baseURL || ''
  const path = err?.url || ''
  const requestLine = method || baseURL || path ? `${method} ${baseURL}${path}`.trim() : ''
  return [detail, status, requestLine].filter(Boolean).join(' | ')
}

export function isInferenceCancelledError(err) {
  const detail = String(err?.detail || err?.message || '').toLowerCase()
  return err?.status === 409 && (detail.includes('取消') || detail.includes('cancel'))
}

export function normalizeAssistantMessage(payload) {
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

export function normalizeMessages(messages) {
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

export function normalizeFeedback(value) {
  return value === 'like' || value === 'dislike' ? value : null
}

export function pickLatestStoredTrace(messages) {
  if (!Array.isArray(messages)) return null
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const item = messages[i]
    if (item?.role === 'assistant' && item?.inference_trace && typeof item.inference_trace === 'object') {
      return item.inference_trace
    }
  }
  return null
}

export function readPinnedConversationIds() {
  try {
    const raw = localStorage.getItem(PINNED_CONVERSATIONS_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.map(id => String(id)).filter(Boolean) : []
  } catch {
    return []
  }
}

export function persistPinnedConversationIds(ids) {
  try {
    localStorage.setItem(PINNED_CONVERSATIONS_KEY, JSON.stringify(ids))
  } catch {
    // ignore persistence failures
  }
}

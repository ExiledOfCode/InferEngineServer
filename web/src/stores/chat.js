import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '../api'
import { ElMessage } from 'element-plus'
import {
  formatApiError,
  isInferenceCancelledError,
  normalizeAssistantMessage,
  normalizeFeedback,
  normalizeMessages,
  persistPinnedConversationIds,
  pickLatestStoredTrace,
  readPinnedConversationIds,
  sanitizeAssistantContent
} from './chat/helpers'

const CHAT_STATUS_POLL_INTERVAL_MS = 500

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const pinnedConversationIds = ref(readPinnedConversationIds())
  const currentConversation = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const canceling = ref(false)
  const loadingConversationId = ref(null)
  const loadingMessageBaselineCount = ref(0)
  const loadingReplyReady = ref(false)
  const creatingConversation = ref(false)
  const switchingModel = ref(false)
  const inferenceStatus = ref(null)
  const inferenceTrace = ref(null)

  function currentConversationId() {
    return String(currentConversation.value?.id || '').trim()
  }

  function isCurrentConversation(id) {
    return currentConversationId() === String(id || '').trim()
  }

  function disabledTracePayload() {
    return {
      state: 'disabled',
      enabled: false,
      steps: []
    }
  }

  function markLoadingReplyStatus(conversationId, loadedMessages) {
    if (String(loadingConversationId.value || '') !== String(conversationId || '')) {
      return false
    }
    const baseline = Number(loadingMessageBaselineCount.value || 0)
    const hasReply = baseline > 0 && Array.isArray(loadedMessages) && loadedMessages.length > baseline
    if (hasReply) {
      loadingReplyReady.value = true
    }
    return hasReply
  }

  function setInferenceTraceForConversation(conversationId, payload) {
    if (!isCurrentConversation(conversationId)) {
      return false
    }
    inferenceTrace.value = payload
    return true
  }

  function traceBelongsToConversation(trace, conversationId) {
    if (!trace || typeof trace !== 'object') {
      return false
    }
    const traceConversationId = trace.conversation_id
    if (traceConversationId === undefined || traceConversationId === null || traceConversationId === '') {
      return true
    }
    return String(traceConversationId) === String(conversationId)
  }

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
    const targetConversation = conversations.value.find(c => c.id === id) || null
    currentConversation.value = targetConversation
    if (!targetConversation) {
      messages.value = []
      inferenceTrace.value = null
      return
    }

    const conversationId = targetConversation.id
    const loaded = normalizeMessages(await chatApi.getMessages(conversationId))
    if (!isCurrentConversation(conversationId)) {
      return
    }

    messages.value = loaded
    markLoadingReplyStatus(conversationId, loaded)
    const storedTrace = pickLatestStoredTrace(loaded)
    if (storedTrace) {
      inferenceTrace.value = storedTrace
      return
    }

    if (!isTraceEnabled()) {
      inferenceTrace.value = disabledTracePayload()
      return
    }

    inferenceTrace.value = null
    if (loading.value && String(loadingConversationId.value || '') === String(conversationId)) {
      try {
        await fetchInferenceTrace({ conversationId })
      } catch {
        // ignore live trace refresh error when switching back to the active conversation
      }
    }
  }

  async function fetchInferenceStatus() {
    inferenceStatus.value = await chatApi.getInferenceStatus()
    return inferenceStatus.value
  }

  async function fetchInferenceTrace(options = {}) {
    const conversationId = options.conversationId ?? currentConversation.value?.id ?? null
    const shouldAssign = options.assign !== false
    if (!isTraceEnabled()) {
      const payload = disabledTracePayload()
      if (shouldAssign && conversationId !== null) {
        setInferenceTraceForConversation(conversationId, payload)
      }
      return payload
    }

    const trace = await chatApi.getInferenceTrace()
    if (
      shouldAssign
      && conversationId !== null
      && traceBelongsToConversation(trace, conversationId)
    ) {
      setInferenceTraceForConversation(conversationId, trace)
    }
    return trace
  }

  async function switchInferenceModel(modelId) {
    const nextId = String(modelId || '').trim()
    if (!nextId || switchingModel.value) {
      return inferenceStatus.value
    }
    switchingModel.value = true
    try {
      inferenceStatus.value = await chatApi.selectInferenceModel(nextId)
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
    const isActiveConversation = () => isCurrentConversation(convId)
    const setTraceIfActive = payload => setInferenceTraceForConversation(convId, payload)
    const refreshMessagesIfActive = async () => {
      const loaded = normalizeMessages(await chatApi.getMessages(convId))
      if (isActiveConversation()) {
        messages.value = loaded
      }
      return loaded
    }
    const pendingAssistantId = `pending-assistant-${Date.now()}`
    const pendingAssistantCreatedAt = new Date().toISOString()
    const replacePendingAssistant = (payload, pending = true) => {
      if (!isActiveConversation()) {
        return
      }
      const normalized = normalizeAssistantMessage(payload)
      const nextMessage = {
        conversation_id: convId,
        role: 'assistant',
        created_at: pendingAssistantCreatedAt,
        ...normalized,
        id: pending ? pendingAssistantId : normalized.id,
        pending
      }
      const existingIndex = messages.value.findIndex(message => message.id === pendingAssistantId)
      if (existingIndex === -1) {
        messages.value.push(nextMessage)
        return
      }
      messages.value.splice(existingIndex, 1, nextMessage)
    }
    const seedPendingAssistant = () => {
      if (!isActiveConversation()) {
        return
      }
      replacePendingAssistant({
        id: pendingAssistantId,
        conversation_id: convId,
        role: 'assistant',
        content: '',
        reasoning_content: null,
        raw_content: null,
        created_at: pendingAssistantCreatedAt
      })
    }
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
    loadingMessageBaselineCount.value = messages.value.length
    seedPendingAssistant()
    loadingReplyReady.value = true
    let traceTimer = null
    let statusTimer = null
    const pollTrace = async () => {
      try {
        await fetchInferenceTrace({ conversationId: convId })
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
      setTraceIfActive(disabledTracePayload())
    }

    try {
      let receivedStreamDelta = false
      let response = null

      try {
        const streamedPayload = await chatApi.streamMessage(convId, content, thinkEnabled, {
          onDelta: payload => {
            receivedStreamDelta = true
            const liveMessage = payload?.message
            if (!liveMessage) {
              return
            }
            replacePendingAssistant(liveMessage)
          },
          onDone: payload => {
            if (payload?.inference_trace) {
              setTraceIfActive(payload.inference_trace)
            }
            if (payload?.message) {
              replacePendingAssistant(payload.message, false)
            }
          }
        })
        response = normalizeAssistantMessage(streamedPayload?.message || streamedPayload)
      } catch (err) {
        if (!receivedStreamDelta && !isInferenceCancelledError(err) && err?.status !== 401) {
          response = normalizeAssistantMessage(await chatApi.sendMessage(convId, content, thinkEnabled))
        } else {
          throw err
        }
      }

      if (response?.inference_trace) {
        setTraceIfActive(response.inference_trace)
      } else if (!isTraceEnabled()) {
        setTraceIfActive(disabledTracePayload())
      }
      try {
        const loaded = await refreshMessagesIfActive()
        markLoadingReplyStatus(convId, loaded)
        if (isActiveConversation() && loaded.length <= 2 && currentConversation.value) {
          currentConversation.value.title = content.slice(0, 50)
        }
      } catch {
        if (isActiveConversation() && response) {
          replacePendingAssistant(response, false)
        }
      }
    } catch (err) {
      if (isInferenceCancelledError(err)) {
        try {
          const loaded = await refreshMessagesIfActive()
          markLoadingReplyStatus(convId, loaded)
          if (
            isActiveConversation()
            && loaded.length <= 2
            && currentConversation.value
            && (!currentConversation.value.title || currentConversation.value.title === '新对话')
          ) {
            currentConversation.value.title = content.slice(0, 50)
          }
        } catch {
          // ignore refresh error after cancel
        }
        return
      }
      try {
        await refreshMessagesIfActive()
      } catch {
        // ignore secondary error
      }
      const detail = formatApiError(err)
      if (isActiveConversation()) {
        replacePendingAssistant({
          id: Date.now() + 1,
          role: 'assistant',
          content: `推理失败: ${sanitizeAssistantContent(detail)}`,
          created_at: new Date().toISOString()
        }, false)
      }
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
          await fetchInferenceTrace({ conversationId: convId })
        } catch {
          // ignore final trace refresh
        }
      } else {
        setTraceIfActive(disabledTracePayload())
      }
      try {
        await fetchInferenceStatus()
      } catch {
        // ignore status refresh failure
      }
      try {
        await fetchConversations()
      } catch {
        // ignore conversation list refresh failure
      }
      loading.value = false
      loadingConversationId.value = null
      loadingMessageBaselineCount.value = 0
      loadingReplyReady.value = false
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
    loadingReplyReady,
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

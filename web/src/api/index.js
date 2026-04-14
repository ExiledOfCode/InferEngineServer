import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const rawBaseURL = (import.meta.env.VITE_API_BASE_URL || '').trim()
const timeout = Number(import.meta.env.VITE_API_TIMEOUT || 300000)
const apiDebug = String(import.meta.env.VITE_API_DEBUG || '').toLowerCase() === 'true'
const isDev = Boolean(import.meta.env.DEV)

function normalizeBaseURL(url) {
  return String(url || '').trim().replace(/\/+$/, '')
}

function inferBaseURLCandidates() {
  if (rawBaseURL) {
    const normalized = normalizeBaseURL(rawBaseURL)
    return normalized ? [normalized] : ['/api']
  }

  const candidates = ['/api']

  if (!isDev && typeof window !== 'undefined') {
    candidates.push(`${window.location.origin}/api`)
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
    const hostname = window.location.hostname || '127.0.0.1'
    candidates.push(`${protocol}//${hostname}:8000/api`)
  }
  candidates.push('http://127.0.0.1:8000/api')
  candidates.push('http://localhost:8000/api')

  const normalized = candidates.map(normalizeBaseURL).filter(Boolean)
  return [...new Set(normalized)]
}

const baseURLCandidates = inferBaseURLCandidates()
let activeBaseURLIndex = 0

function getActiveBaseURL() {
  return baseURLCandidates[activeBaseURLIndex] || '/api'
}

const api = axios.create({ baseURL: getActiveBaseURL(), timeout })

function buildRequestUrl(config) {
  const url = String(config?.url || '')
  if (/^https?:\/\//i.test(url)) {
    return url
  }
  const base = normalizeBaseURL(config?.baseURL || getActiveBaseURL())
  return `${base}${url}`
}

function normalizeError(error) {
  const status = error?.response?.status
  const responseData = error?.response?.data
  const message = responseData?.detail || error?.message || '请求失败'
  return {
    detail: typeof message === 'string' ? message : JSON.stringify(message),
    status,
    data: responseData,
    url: error?.config?.url,
    method: error?.config?.method,
    baseURL: error?.config?.baseURL || getActiveBaseURL()
  }
}

api.interceptors.request.use(config => {
  config.baseURL = getActiveBaseURL()

  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  if (apiDebug) {
    config.metadata = { startAt: Date.now() }
    // eslint-disable-next-line no-console
    console.log(`[api] -> ${String(config.method || 'GET').toUpperCase()} ${buildRequestUrl(config)}`)
  }
  return config
}, error => Promise.reject(normalizeError(error)))

function shouldRetryWithFallback(error) {
  if (rawBaseURL || baseURLCandidates.length <= 1) {
    return false
  }
  const config = error?.config
  if (!config) {
    return false
  }
  const retryCount = Number(config.__baseRetryCount || 0)
  if (retryCount >= baseURLCandidates.length - 1) {
    return false
  }
  const status = error?.response?.status
  if (status === 401 || status === 403) {
    return false
  }
  if (!error?.response) {
    return true
  }
  return [404, 405, 500, 502, 503, 504].includes(status)
}

function moveToNextBaseURL() {
  if (activeBaseURLIndex + 1 >= baseURLCandidates.length) {
    return null
  }
  activeBaseURLIndex += 1
  return getActiveBaseURL()
}

api.interceptors.response.use(
  response => {
    if (apiDebug) {
      const startAt = response.config?.metadata?.startAt
      const costMs = startAt ? Date.now() - startAt : -1
      // eslint-disable-next-line no-console
      console.log(`[api] <- ${response.status} ${buildRequestUrl(response.config)} ${costMs}ms`)
    }
    return response.data
  },
  async error => {
    if (shouldRetryWithFallback(error)) {
      const nextBaseURL = moveToNextBaseURL()
      if (nextBaseURL) {
        const config = error.config
        config.__baseRetryCount = Number(config.__baseRetryCount || 0) + 1
        config.baseURL = nextBaseURL
        if (apiDebug) {
          // eslint-disable-next-line no-console
          console.warn(`[api] retry #${config.__baseRetryCount} with fallback baseURL: ${nextBaseURL}`)
        }
        return api.request(config)
      }
    }

    if (error?.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
    }
    const normalized = normalizeError(error)
    if (apiDebug) {
      // eslint-disable-next-line no-console
      console.error('[api] xx', normalized)
    }
    return Promise.reject(normalized)
  }
)

if (apiDebug) {
  // eslint-disable-next-line no-console
  console.log(`[api] baseURL candidates: ${baseURLCandidates.join(', ')}`)
}

export const authApi = {
  login: (data) => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout')
}

export const adminApi = {
  getStats: () => api.get('/admin/stats'),
  getInferenceStatus: () => api.get('/admin/inference/status'),
  getInferenceOptions: () => api.get('/admin/inference/options'),
  updateInferenceOptions: (data) => api.put('/admin/inference/options', data),
  getUsers: () => api.get('/admin/users'),
  createUser: (data) => api.post('/admin/users', data),
  updateUser: (id, data) => api.put(`/admin/users/${id}`, data),
  deleteUser: (id) => api.delete(`/admin/users/${id}`)
}

export const chatApi = {
  getConversations: () => api.get('/conversations'),
  createConversation: (data = {}) => api.post('/conversations', data),
  deleteConversation: (id) => api.delete(`/conversations/${id}`),
  getMessages: (id) => api.get(`/conversations/${id}/messages`),
  sendMessage: (id, content) => api.post(`/conversations/${id}/messages`, { content }),
  cancelInference: () => api.post('/inference/cancel'),
  getInferenceStatus: () => api.get('/inference/status'),
  getInferenceTrace: () => api.get('/inference/trace'),
  getInferenceModels: () => api.get('/inference/models'),
  selectInferenceModel: (modelId) => api.post('/inference/model/select', { model_id: modelId })
}

export default api

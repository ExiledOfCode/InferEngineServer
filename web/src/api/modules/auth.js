import api from '../http'

export const authApi = {
  login: data => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout')
}

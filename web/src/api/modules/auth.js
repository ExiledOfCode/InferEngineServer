// 文件说明：前端 API 模块，封装 auth 相关后端接口调用。

import api from '../http'

export const authApi = {
  login: data => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout')
}

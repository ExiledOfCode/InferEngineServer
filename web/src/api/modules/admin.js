// 文件说明：前端 API 模块，封装 admin 相关后端接口调用。

import api from '../http'

export const adminApi = {
  getStats: () => api.get('/admin/stats'),
  getInferenceStatus: () => api.get('/admin/inference/status'),
  getInferenceOptions: () => api.get('/admin/inference/options'),
  updateInferenceOptions: data => api.put('/admin/inference/options', data),
  getOperatorOptions: () => api.get('/admin/operator/options'),
  updateOperatorOptions: data => api.put('/admin/operator/options', data),
  getUsers: () => api.get('/admin/users'),
  createUser: data => api.post('/admin/users', data),
  updateUser: (id, data) => api.put(`/admin/users/${id}`, data),
  deleteUser: id => api.delete(`/admin/users/${id}`)
}

<template>
  <AdminShell active-view="users">
    <header class="admin-header">
      <div>
        <h2>用户管理</h2>
        <p>创建、启用、禁用或重置普通用户账号。</p>
      </div>
      <el-button class="create-btn" type="primary" @click="showCreate">
        <el-icon><Plus /></el-icon>
        <span>创建用户</span>
      </el-button>
    </header>

    <div class="table-card">
      <el-table :data="users" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
              {{ row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="190">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggle(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" @click="showReset(row)">重置密码</el-button>
            <el-button size="small" type="danger" @click="del(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="createVisible" title="创建用户" width="420px">
      <el-form :model="createForm" ref="createRef" label-width="82px">
        <el-form-item label="用户名" prop="username" :rules="[{ required: true, message: '必填' }]">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="密码" prop="password" :rules="[{ required: true, message: '必填' }]">
          <el-input v-model="createForm.password" type="password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="create">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <el-form :model="resetForm" ref="resetRef" label-width="82px">
        <el-form-item label="新密码" prop="password" :rules="[{ required: true, message: '必填' }]">
          <el-input v-model="resetForm.password" type="password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" @click="reset">确定</el-button>
      </template>
    </el-dialog>
  </AdminShell>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminApi } from '../../api'
import AdminShell from './components/AdminShell.vue'

const users = ref([])
const createVisible = ref(false)
const resetVisible = ref(false)
const currentUser = ref(null)
const createForm = reactive({ username: '', password: '' })
const resetForm = reactive({ password: '' })
const createRef = ref(null)
const resetRef = ref(null)

onMounted(() => fetchUsers())

async function fetchUsers() {
  try {
    users.value = await adminApi.getUsers()
  } catch (e) {
    ElMessage.error(e?.detail || '加载用户列表失败')
  }
}

function showCreate() {
  createForm.username = ''
  createForm.password = ''
  createVisible.value = true
}

function showReset(user) {
  currentUser.value = user
  resetForm.password = ''
  resetVisible.value = true
}

async function create() {
  try {
    await createRef.value.validate()
    await adminApi.createUser(createForm)
    ElMessage.success('创建成功')
    createVisible.value = false
    await fetchUsers()
  } catch (e) {
    ElMessage.error(e?.detail || '创建失败')
  }
}

async function reset() {
  try {
    await resetRef.value.validate()
    await adminApi.updateUser(currentUser.value.id, { password: resetForm.password })
    ElMessage.success('重置成功')
    resetVisible.value = false
  } catch (e) {
    ElMessage.error(e?.detail || '重置失败')
  }
}

async function toggle(user) {
  try {
    const nextStatus = user.status === 'active' ? 'disabled' : 'active'
    await adminApi.updateUser(user.id, { status: nextStatus })
    user.status = nextStatus
    ElMessage.success('更新成功')
  } catch (e) {
    ElMessage.error(e?.detail || '更新失败')
  }
}

async function del(user) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${user.username}」吗？`, '删除确认', { type: 'warning' })
    await adminApi.deleteUser(user.id)
    ElMessage.success('删除成功')
    await fetchUsers()
  } catch {
    // ignore cancel
  }
}
</script>

<style scoped>
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.admin-header h2 {
  font-size: 28px;
  color: #111827;
}

.admin-header p {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 14px;
}

.create-btn {
  border-radius: 12px;
  border: none;
  height: 40px;
  padding: 0 16px;
  background: linear-gradient(135deg, #10a37f, #0f7d62);
}

.table-card {
  margin-top: 18px;
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--shadow-card);
  padding: 10px 12px;
}

.table-card :deep(.el-table) {
  --el-table-header-bg-color: #f7f9fc;
  --el-table-row-hover-bg-color: #f5f8fd;
  border-radius: 12px;
}

.table-card :deep(.el-table__cell) {
  padding: 12px 0;
}

@media (max-width: 980px) {
  .admin-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

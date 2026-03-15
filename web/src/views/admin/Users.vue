<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark">江</div>
        <div class="brand-text">
          <h1>江屿大模型</h1>
          <p>管理控制台</p>
        </div>
      </div>

      <nav class="sidebar-nav">
        <button class="nav-item" @click="router.push('/admin/dashboard')">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </button>
        <button class="nav-item active" @click="router.push('/admin/users')">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="admin-meta">
          <div class="avatar">{{ (authStore.user?.username || 'A').slice(0, 1).toUpperCase() }}</div>
          <div class="meta-text">
            <span class="name">{{ authStore.user?.username }}</span>
            <span class="role">Administrator</span>
          </div>
        </div>
        <button class="logout-btn" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <section class="admin-main">
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
    </section>

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { adminApi } from '../../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
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

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-shell {
  min-height: 100vh;
  display: flex;
  background: linear-gradient(180deg, #f8fafd 0%, #f4f7fb 100%);
}

.admin-sidebar {
  width: 268px;
  border-right: 1px solid var(--border-subtle);
  background: #eceff4;
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
  gap: 14px;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px 12px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(135deg, #10a37f, #0f7d62);
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-text h1 {
  font-size: 16px;
  color: #111827;
  line-height: 1.1;
}

.brand-text p {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 12px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  border: 0;
  width: 100%;
  height: 42px;
  border-radius: 12px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
}

.nav-item:hover {
  background: #dfe4ec;
}

.nav-item.active {
  background: #d9e3f2;
  color: #1f2a3b;
  font-weight: 600;
}

.sidebar-foot {
  margin-top: auto;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: #f7f9fc;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.admin-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(140deg, #2f4a80, #1f2f52);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.meta-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.role {
  color: var(--text-muted);
  font-size: 11px;
}

.logout-btn {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.logout-btn:hover {
  background: #e8edf5;
}

.admin-main {
  flex: 1;
  min-width: 0;
  padding: 28px 28px 24px;
}

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
  .admin-shell {
    flex-direction: column;
  }

  .admin-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--border-subtle);
  }

  .admin-main {
    padding: 20px 14px 14px;
  }

  .admin-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

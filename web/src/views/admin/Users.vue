<template>
  <AdminShell active-view="users">
    <div class="admin-page">
      <header class="admin-page-hero">
        <div>
          <span class="admin-page-kicker">Users</span>
          <h2 class="admin-page-title">用户管理</h2>
          <p class="admin-page-description">
            集中处理普通用户账号的创建、启用禁用、密码重置和清理操作。
          </p>
        </div>

        <div class="admin-page-hero__aside">
          <article class="hero-info-card">
            <div class="hero-info-label">总用户数</div>
            <div class="hero-info-value">{{ users.length }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">正常账号</div>
            <div class="hero-info-value">{{ activeUserCount }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">禁用账号</div>
            <div class="hero-info-value">{{ disabledUserCount }}</div>
          </article>
        </div>
      </header>

      <div class="summary-strip">
        <article class="summary-strip-card">
          <div class="summary-strip-label">默认操作</div>
          <div class="summary-strip-value">创建</div>
        </article>
        <article class="summary-strip-card">
          <div class="summary-strip-label">高频维护</div>
          <div class="summary-strip-value">重置密码</div>
        </article>
        <article class="summary-strip-card">
          <div class="summary-strip-label">风险操作</div>
          <div class="summary-strip-value">删除账号</div>
        </article>
      </div>

      <section class="panel-card table-card">
        <div class="table-toolbar">
          <div class="table-toolbar-copy">
            <h3>账号列表</h3>
            <p>支持启用、禁用、重置密码和删除操作。</p>
          </div>
          <el-button class="action-primary-btn" type="primary" @click="showCreate">
            <el-icon><Plus /></el-icon>
            <span>创建用户</span>
          </el-button>
        </div>

        <el-table :data="users" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="username" label="用户名" min-width="180" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
                {{ row.status === 'active' ? '正常' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="200">
            <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="290">
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
  </AdminShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
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

const activeUserCount = computed(() => users.value.filter(user => user.status === 'active').length)
const disabledUserCount = computed(() => users.value.filter(user => user.status !== 'active').length)

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

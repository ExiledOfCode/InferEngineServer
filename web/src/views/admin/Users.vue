<template>
  <div class="admin-container">
    <div class="admin-sidebar">
      <h2>管理后台</h2>
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/admin/dashboard"><el-icon><DataAnalysis /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/admin/users"><el-icon><User /></el-icon><span>用户管理</span></el-menu-item>
      </el-menu>
      <div class="admin-user" @click="handleLogout"><el-icon><SwitchButton /></el-icon><span>退出登录</span></div>
    </div>
    <div class="admin-main">
      <div class="page-header"><h1>用户管理</h1><el-button type="primary" @click="showCreate"><el-icon><Plus /></el-icon>创建用户</el-button></div>
      <el-table :data="users" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'danger'">{{ row.status === 'active' ? '正常' : '禁用' }}</el-tag></template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="250"><template #default="{ row }">
          <el-button size="small" :type="row.status === 'active' ? 'warning' : 'success'" @click="toggle(row)">{{ row.status === 'active' ? '禁用' : '启用' }}</el-button>
          <el-button size="small" @click="showReset(row)">重置密码</el-button>
          <el-button size="small" type="danger" @click="del(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="createVisible" title="创建用户" width="400px">
      <el-form :model="createForm" ref="createRef" label-width="80px">
        <el-form-item label="用户名" prop="username" :rules="[{ required: true, message: '必填' }]"><el-input v-model="createForm.username" /></el-form-item>
        <el-form-item label="密码" prop="password" :rules="[{ required: true, message: '必填' }]"><el-input v-model="createForm.password" type="password" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" @click="create">确定</el-button></template>
    </el-dialog>
    <el-dialog v-model="resetVisible" title="重置密码" width="400px">
      <el-form :model="resetForm" ref="resetRef" label-width="80px">
        <el-form-item label="新密码" prop="password" :rules="[{ required: true, message: '必填' }]"><el-input v-model="resetForm.password" type="password" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="resetVisible = false">取消</el-button><el-button type="primary" @click="reset">确定</el-button></template>
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

onMounted(() => fetch())
async function fetch() { users.value = await adminApi.getUsers() }
function showCreate() { createForm.username = ''; createForm.password = ''; createVisible.value = true }
function showReset(u) { currentUser.value = u; resetForm.password = ''; resetVisible.value = true }
async function create() { try { await createRef.value.validate(); await adminApi.createUser(createForm); ElMessage.success('创建成功'); createVisible.value = false; fetch() } catch (e) { ElMessage.error(e.detail || '失败') } }
async function reset() { try { await resetRef.value.validate(); await adminApi.updateUser(currentUser.value.id, { password: resetForm.password }); ElMessage.success('重置成功'); resetVisible.value = false } catch (e) { ElMessage.error(e.detail || '失败') } }
async function toggle(u) { try { await adminApi.updateUser(u.id, { status: u.status === 'active' ? 'disabled' : 'active' }); u.status = u.status === 'active' ? 'disabled' : 'active'; ElMessage.success('成功') } catch (e) { ElMessage.error('失败') } }
async function del(u) { try { await ElMessageBox.confirm('确定删除？'); await adminApi.deleteUser(u.id); ElMessage.success('删除成功'); fetch() } catch {} }
function handleLogout() { authStore.logout(); router.push('/login') }
</script>

<style scoped>
.admin-container { display: flex; height: 100vh; }
.admin-sidebar { width: 220px; background: #304156; display: flex; flex-direction: column; }
.admin-sidebar h2 { color: white; padding: 20px; margin: 0; }
.admin-sidebar .el-menu { flex: 1; border: none; background: transparent; }
.admin-sidebar :deep(.el-menu-item) { color: #bfcbd9; }
.admin-sidebar :deep(.el-menu-item.is-active) { color: #409EFF; background: #263445; }
.admin-user { display: flex; align-items: center; gap: 10px; padding: 20px; color: #bfcbd9; cursor: pointer; border-top: 1px solid #3b4a5a; }
.admin-main { flex: 1; padding: 30px; background: #f5f7fa; overflow-y: auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h1 { margin: 0; color: #333; }
</style>

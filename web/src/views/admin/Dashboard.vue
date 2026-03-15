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
      <h1>仪表盘</h1>
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-icon user"><el-icon><User /></el-icon></div><div class="stat-info"><div class="stat-value">{{ stats.user_count }}</div><div class="stat-label">用户数量</div></div></div>
        <div class="stat-card"><div class="stat-icon conv"><el-icon><ChatDotRound /></el-icon></div><div class="stat-info"><div class="stat-value">{{ stats.conversation_count }}</div><div class="stat-label">对话数量</div></div></div>
        <div class="stat-card"><div class="stat-icon msg"><el-icon><Comment /></el-icon></div><div class="stat-info"><div class="stat-value">{{ stats.message_count }}</div><div class="stat-label">消息数量</div></div></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { adminApi } from '../../api'

const router = useRouter()
const authStore = useAuthStore()
const stats = ref({ user_count: 0, conversation_count: 0, message_count: 0 })
onMounted(async () => { stats.value = await adminApi.getStats() })
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
.admin-main { flex: 1; padding: 30px; background: #f5f7fa; }
.admin-main h1 { margin: 0 0 30px; color: #333; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
.stat-card { background: white; border-radius: 12px; padding: 24px; display: flex; align-items: center; gap: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
.stat-icon { width: 60px; height: 60px; border-radius: 12px; display: flex; justify-content: center; align-items: center; font-size: 28px; color: white; }
.stat-icon.user { background: linear-gradient(135deg, #667eea, #764ba2); }
.stat-icon.conv { background: linear-gradient(135deg, #f093fb, #f5576c); }
.stat-icon.msg { background: linear-gradient(135deg, #4facfe, #00f2fe); }
.stat-value { font-size: 32px; font-weight: 600; color: #333; }
.stat-label { color: #999; margin-top: 4px; }
</style>

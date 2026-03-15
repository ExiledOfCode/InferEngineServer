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
        <button class="nav-item active" @click="router.push('/admin/dashboard')">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </button>
        <button class="nav-item" @click="router.push('/admin/users')">
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
        <h2>仪表盘</h2>
        <p>实时查看平台用户、会话与消息总量。</p>
      </header>

      <div class="stats-grid">
        <article class="stat-card">
          <div class="stat-icon user"><el-icon><User /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.user_count }}</div>
            <div class="stat-label">用户数量</div>
          </div>
        </article>

        <article class="stat-card">
          <div class="stat-icon conv"><el-icon><ChatDotRound /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.conversation_count }}</div>
            <div class="stat-label">对话数量</div>
          </div>
        </article>

        <article class="stat-card">
          <div class="stat-icon msg"><el-icon><Comment /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.message_count }}</div>
            <div class="stat-label">消息数量</div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { adminApi } from '../../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const stats = ref({ user_count: 0, conversation_count: 0, message_count: 0 })

onMounted(async () => {
  try {
    stats.value = await adminApi.getStats()
  } catch (e) {
    ElMessage.error(e?.detail || '加载统计信息失败')
  }
})

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
  padding: 28px 28px 24px;
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

.stats-grid {
  margin-top: 22px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.stat-card {
  border-radius: 16px;
  border: 1px solid var(--border-subtle);
  background: #fff;
  box-shadow: var(--shadow-card);
  padding: 18px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  color: #fff;
  font-size: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon.user { background: linear-gradient(135deg, #3f6ac3, #3456a8); }
.stat-icon.conv { background: linear-gradient(135deg, #10a37f, #0f7d62); }
.stat-icon.msg { background: linear-gradient(135deg, #5f75a3, #4a5d84); }

.stat-value {
  font-size: 30px;
  line-height: 1;
  font-weight: 700;
  color: #1f2937;
}

.stat-label {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 920px) {
  .admin-shell {
    flex-direction: column;
  }

  .admin-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--border-subtle);
  }
}
</style>

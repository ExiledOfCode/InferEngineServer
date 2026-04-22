<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark">江</div>
        <div class="brand-text">
          <h1>自研推理引擎对话平台</h1>
          <p>管理控制台</p>
        </div>
      </div>

      <nav class="sidebar-nav">
        <button class="nav-item" :class="{ active: activeView === 'dashboard' }" @click="router.push('/admin/dashboard')">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </button>
        <button class="nav-item" :class="{ active: activeView === 'users' }" @click="router.push('/admin/users')">
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
      <slot />
    </section>
  </div>
</template>

<script setup>
import { DataAnalysis, SwitchButton, User } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../../../stores/auth'

defineProps({
  activeView: {
    type: String,
    required: true
  }
})

const router = useRouter()
const authStore = useAuthStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style src="../admin-shell.css"></style>

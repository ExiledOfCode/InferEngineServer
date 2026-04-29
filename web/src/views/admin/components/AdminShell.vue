<!-- 文件说明：管理后台布局组件，封装侧栏导航、用户信息和退出入口。 -->

<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="sidebar-brand">
        <div class="brand-mark">控</div>
        <div class="brand-text">
          <h1>自研推理引擎对话平台</h1>
          <p>管理控制台</p>
        </div>
      </div>

      <div class="sidebar-label">Console</div>
      <nav class="sidebar-nav">
        <button
          v-for="item in navItems"
          :key="item.id"
          class="nav-item"
          :class="{ active: activeView === item.id }"
          @click="router.push(item.path)"
        >
          <span class="nav-item-icon">
            <el-icon><component :is="item.icon" /></el-icon>
          </span>
          <span class="nav-item-copy">
            <strong>{{ item.label }}</strong>
            <small>{{ item.caption }}</small>
          </span>
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
          <span class="logout-btn-icon">
            <el-icon><SwitchButton /></el-icon>
          </span>
          <span>退出登录</span>
        </button>
      </div>
    </aside>

    <section class="admin-main">
      <div class="admin-main__inner">
        <slot />
      </div>
    </section>
  </div>
</template>

<script setup>
import { DataAnalysis, Operation, Setting, SwitchButton, User } from '@element-plus/icons-vue'
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
const navItems = [
  {
    id: 'dashboard',
    label: '仪表盘',
    caption: '平台状态与快捷入口',
    path: '/admin/dashboard',
    icon: DataAnalysis
  },
  {
    id: 'users',
    label: '用户管理',
    caption: '账号、状态与重置密码',
    path: '/admin/users',
    icon: User
  },
  {
    id: 'engine',
    label: '引擎优化',
    caption: '推理进程与生成参数',
    path: '/admin/engine',
    icon: Setting
  },
  {
    id: 'operators',
    label: '算子优化',
    caption: 'kernel 版本与启动路径',
    path: '/admin/operators',
    icon: Operation
  }
]

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style src="../admin-shell.css"></style>
<style src="../admin-panels.css"></style>

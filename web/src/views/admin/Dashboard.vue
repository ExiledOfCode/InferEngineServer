<!-- 文件说明：管理后台首页，展示统计指标和配置快捷入口。 -->

<template>
  <AdminShell active-view="dashboard">
    <div class="admin-page">
      <header class="admin-page-hero">
        <div>
          <span class="admin-page-kicker">Overview</span>
          <h2 class="admin-page-title">管理总览</h2>
          <p class="admin-page-description">
            仪表盘只保留平台状态和快捷入口，避免把用户、引擎、算子三类能力继续堆在一个页面里。
          </p>
        </div>

        <div class="admin-page-hero__aside">
          <article class="hero-info-card">
            <div class="hero-info-label">引擎状态</div>
            <div class="hero-info-value">{{ inferenceOptions.running ? '在线运行中' : '未启动' }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">当前模型</div>
            <div class="hero-info-value">{{ currentModelName }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">上下文长度</div>
            <div class="hero-info-value">{{ currentModelSeqLenText }}</div>
          </article>
        </div>
      </header>

      <div class="admin-grid-single">
        <DashboardStatsPanel :stats="stats" />
        <DashboardShortcutPanel />
      </div>
    </div>
  </AdminShell>
</template>

<script setup>
import AdminShell from './components/AdminShell.vue'
import DashboardShortcutPanel from './components/DashboardShortcutPanel.vue'
import DashboardStatsPanel from './components/DashboardStatsPanel.vue'
import { useAdminStats, useInferenceOptionsControl } from './useAdminDashboard'

const { stats } = useAdminStats()
const {
  currentModelName,
  currentModelSeqLenText,
  inferenceOptions
} = useInferenceOptionsControl()
</script>

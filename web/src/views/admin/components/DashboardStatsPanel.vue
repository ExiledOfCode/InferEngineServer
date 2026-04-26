<template>
  <section class="panel-card panel-card-stats stats-panel">
    <div class="panel-head">
      <div>
        <h3>平台统计</h3>
        <p>查看平台当前的用户规模、会话累积量和消息吞吐基础数据。</p>
      </div>
    </div>

    <div class="stats-grid">
      <article class="stat-card">
        <div class="stat-icon user"><el-icon><User /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.user_count }}</div>
          <div class="stat-label">用户数量</div>
          <div class="stat-meta">包含当前所有普通用户账号</div>
        </div>
      </article>

      <article class="stat-card">
        <div class="stat-icon conv"><el-icon><ChatDotRound /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.conversation_count }}</div>
          <div class="stat-label">对话数量</div>
          <div class="stat-meta">累计创建的会话总数</div>
        </div>
      </article>

      <article class="stat-card">
        <div class="stat-icon msg"><el-icon><Comment /></el-icon></div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.message_count }}</div>
          <div class="stat-label">消息数量</div>
          <div class="stat-meta">覆盖用户与助手全部消息</div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { ChatDotRound, Comment, User } from '@element-plus/icons-vue'

defineProps({
  stats: {
    type: Object,
    required: true
  }
})
</script>

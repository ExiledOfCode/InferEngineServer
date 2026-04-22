<template>
  <AdminShell active-view="dashboard">
    <header class="admin-header">
      <h2>仪表盘</h2>
      <p>实时查看平台统计数据，并在这里切换引擎优化项。</p>
    </header>

    <div class="dashboard-grid">
      <section class="panel-card">
        <div class="panel-head">
          <div>
            <h3>平台统计</h3>
            <p>当前注册用户、对话与消息总量。</p>
          </div>
        </div>

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

      <section class="panel-card">
        <div class="panel-head">
          <div>
            <h3>引擎优化</h3>
            <p>未来新增的性能开关会继续挂到这里，支持逐项开启和关闭。</p>
          </div>
          <div class="panel-head-icon">
            <el-icon><Setting /></el-icon>
          </div>
        </div>

        <div class="engine-summary">
          <article class="summary-card">
            <div class="summary-label">当前模型</div>
            <div class="summary-value">{{ currentModelName }}</div>
          </article>
          <article class="summary-card">
            <div class="summary-label">上下文长度</div>
            <div class="summary-value">{{ currentModelSeqLenText }}</div>
          </article>
          <article class="summary-card">
            <div class="summary-label">引擎状态</div>
            <div class="summary-value">
              <span class="status-pill" :class="{ online: inferenceOptions.running }">
                {{ inferenceOptions.running ? '在线' : '离线' }}
              </span>
            </div>
          </article>
          <article class="summary-card">
            <div class="summary-label">埋点状态</div>
            <div class="summary-value">{{ inferenceOptions.trace_enabled ? '开启' : '关闭' }}</div>
          </article>
        </div>

        <div class="runtime-path" v-if="inferenceOptions.runtime_options_path">
          <span class="runtime-label">运行时配置文件</span>
          <code>{{ inferenceOptions.runtime_options_path }}</code>
        </div>

        <div class="setting-item">
          <div class="option-meta">
            <div class="option-title-row">
              <span class="option-title">max_token</span>
              <span class="option-tag">影响 think 长度与最终回答完整度</span>
            </div>
            <p class="option-desc">
              当前值 {{ inferenceOptions.max_new_tokens }}。当前模型上下文长度为 {{ currentModelSeqLenText }}，
              实际安全条件是 prompt token + max_token 不超过上下文长度。
            </p>
          </div>
          <div class="token-editor">
            <el-input-number
              v-model="draftMaxNewTokens"
              :min="inferenceOptions.min_max_new_tokens || 16"
              :step="16"
              controls-position="right"
            />
            <el-button
              type="primary"
              :loading="savingMaxNewTokens"
              @click="handleMaxNewTokensSave"
            >
              应用
            </el-button>
          </div>
        </div>

        <div class="setting-item">
          <div class="option-meta">
            <div class="option-title-row">
              <span class="option-title">temperature</span>
              <span class="option-tag">0 为确定性输出</span>
            </div>
            <p class="option-desc">
              当前值 {{ inferenceOptions.temperature }}，调高后会按概率采样生成 token。
            </p>
          </div>
          <div class="token-editor">
            <el-input-number
              v-model="draftTemperature"
              :min="inferenceOptions.min_temperature ?? 0"
              :max="inferenceOptions.max_temperature ?? 2"
              :step="0.1"
              :precision="2"
              controls-position="right"
            />
            <el-button
              type="primary"
              :loading="savingTemperature"
              @click="handleTemperatureSave"
            >
              应用
            </el-button>
          </div>
        </div>

        <div class="option-list">
          <article
            v-for="option in inferenceOptions.options"
            :key="option.id"
            class="option-item"
          >
            <div class="option-meta">
              <div class="option-title-row">
                <span class="option-title">{{ option.name }}</span>
                <span v-if="option.requires_restart" class="option-tag">需要重启当前引擎</span>
              </div>
              <p class="option-desc">{{ option.description || '暂无说明' }}</p>
            </div>
            <el-switch
              :model-value="option.enabled"
              :loading="savingOptionIds.includes(option.id)"
              @change="value => handleOptionChange(option, value)"
            />
          </article>
        </div>

        <div v-if="!inferenceOptions.options.length" class="empty-hint">
          当前没有可配置的优化项。
        </div>
      </section>
    </div>
  </AdminShell>
</template>

<script setup>
import { ChatDotRound, Comment, Setting, User } from '@element-plus/icons-vue'

import AdminShell from './components/AdminShell.vue'
import { useAdminDashboard } from './useAdminDashboard'

const {
  currentModelName,
  currentModelSeqLenText,
  draftMaxNewTokens,
  draftTemperature,
  handleMaxNewTokensSave,
  handleOptionChange,
  handleTemperatureSave,
  inferenceOptions,
  savingMaxNewTokens,
  savingOptionIds,
  savingTemperature,
  stats
} = useAdminDashboard()
</script>

<style scoped src="./dashboard.css"></style>

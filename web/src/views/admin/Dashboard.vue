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
                当前值 {{ inferenceOptions.max_new_tokens }}，可在这里直接调整生成步数上限。
              </p>
            </div>
            <div class="token-editor">
              <el-input-number
                v-model="draftMaxNewTokens"
                :min="inferenceOptions.min_max_new_tokens || 16"
                :max="inferenceOptions.max_max_new_tokens || 2048"
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
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Comment, DataAnalysis, Setting, SwitchButton, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'
import { adminApi } from '../../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const stats = ref({ user_count: 0, conversation_count: 0, message_count: 0 })
const inferenceOptions = ref({
  current_model_name: '',
  running: false,
  ready: false,
  trace_enabled: true,
  warmup_on_model_switch: true,
  max_new_tokens: 128,
  default_max_new_tokens: 128,
  min_max_new_tokens: 16,
  max_max_new_tokens: 2048,
  runtime_options_path: '',
  options: []
})
const savingOptionIds = ref([])
const draftMaxNewTokens = ref(128)
const savingMaxNewTokens = ref(false)

const currentModelName = computed(() => inferenceOptions.value.current_model_name || '未选择模型')

onMounted(async () => {
  await Promise.all([fetchStats(), fetchInferenceOptions()])
})

async function fetchStats() {
  try {
    stats.value = await adminApi.getStats()
  } catch (e) {
    ElMessage.error(e?.detail || '加载统计信息失败')
  }
}

async function fetchInferenceOptions() {
  try {
    inferenceOptions.value = await adminApi.getInferenceOptions()
    draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || 128)
  } catch (e) {
    ElMessage.error(e?.detail || '加载引擎优化配置失败')
  }
}

async function handleOptionChange(option, enabled) {
  const previous = option.enabled
  if (previous === enabled) {
    return
  }

  savingOptionIds.value = [...savingOptionIds.value, option.id]
  try {
    inferenceOptions.value = await adminApi.updateInferenceOptions({
      options: {
        [option.id]: enabled
      }
    })
    draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || draftMaxNewTokens.value)
    ElMessage.success(`${option.name}已${enabled ? '开启' : '关闭'}`)
  } catch (e) {
    option.enabled = previous
    ElMessage.error(e?.detail || '更新引擎优化项失败')
    await fetchInferenceOptions()
  } finally {
    savingOptionIds.value = savingOptionIds.value.filter(id => id !== option.id)
  }
}

async function handleMaxNewTokensSave() {
  const nextValue = Number(draftMaxNewTokens.value || 0)
  if (!Number.isFinite(nextValue)) {
    ElMessage.error('max_token 必须是数字')
    return
  }

  const currentValue = Number(inferenceOptions.value.max_new_tokens || 0)
  if (nextValue === currentValue) {
    return
  }

  savingMaxNewTokens.value = true
  try {
    inferenceOptions.value = await adminApi.updateInferenceOptions({
      max_new_tokens: nextValue
    })
    draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || nextValue)
    ElMessage.success(`max_token 已更新为 ${inferenceOptions.value.max_new_tokens}`)
  } catch (e) {
    draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || currentValue || 128)
    ElMessage.error(e?.detail || '更新 max_token 失败')
  } finally {
    savingMaxNewTokens.value = false
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

.dashboard-grid {
  margin-top: 22px;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.2fr);
  gap: 16px;
  align-items: start;
}

.panel-card {
  border-radius: 18px;
  border: 1px solid var(--border-subtle);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-card);
  padding: 18px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h3 {
  font-size: 18px;
  color: #1f2937;
}

.panel-head p {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.panel-head-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: #eff5fc;
  color: #355a96;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.stats-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
}

.stat-card {
  border-radius: 16px;
  border: 1px solid var(--border-subtle);
  background: #fff;
  padding: 18px;
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

.engine-summary {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  border-radius: 14px;
  background: #f6f9fc;
  border: 1px solid #e3eaf4;
  padding: 14px;
}

.summary-label {
  font-size: 12px;
  color: var(--text-muted);
}

.summary-value {
  margin-top: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  word-break: break-word;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 62px;
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: #eef2f8;
  color: #4b5563;
  font-size: 13px;
}

.status-pill.online {
  background: rgba(16, 163, 127, 0.14);
  color: #0f7d62;
}

.runtime-path {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #0f172a;
  color: #d8e0ee;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.runtime-label {
  font-size: 12px;
  color: #9fb1cc;
}

.runtime-path code {
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.setting-item {
  margin-top: 16px;
  border-radius: 14px;
  border: 1px solid #e3eaf4;
  background: #fff;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.token-editor {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.option-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-item {
  border-radius: 14px;
  border: 1px solid #e3eaf4;
  background: #fff;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.option-meta {
  min-width: 0;
}

.option-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.option-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.option-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: #eef3fb;
  color: #45608f;
  font-size: 12px;
}

.option-desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.empty-hint {
  margin-top: 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1080px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
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

  .engine-summary {
    grid-template-columns: 1fr;
  }

  .option-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .token-editor {
    width: 100%;
  }
}
</style>

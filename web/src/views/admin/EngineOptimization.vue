<template>
  <AdminShell active-view="engine">
    <div class="admin-page">
      <header class="admin-page-hero">
        <div>
          <span class="admin-page-kicker">Engine</span>
          <h2 class="admin-page-title">引擎优化</h2>
          <p class="admin-page-description">
            单独维护推理进程级别的能力，包括埋点、连续权重加载、分页 KV cache，以及生成相关参数。
          </p>
        </div>

        <div class="admin-page-hero__aside">
          <article class="hero-info-card">
            <div class="hero-info-label">当前模型</div>
            <div class="hero-info-value">{{ currentModelName }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">上下文长度</div>
            <div class="hero-info-value">{{ currentModelSeqLenText }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">埋点状态</div>
            <div class="hero-info-value">{{ inferenceOptions.trace_enabled ? '已开启' : '已关闭' }}</div>
          </article>
        </div>
      </header>

      <div class="admin-grid-single">
        <EngineOptionsPanel
          :current-model-name="currentModelName"
          :current-model-seq-len-text="currentModelSeqLenText"
          :draft-max-new-tokens="draftMaxNewTokens"
          :draft-temperature="draftTemperature"
          :inference-options="inferenceOptions"
          :saving-max-new-tokens="savingMaxNewTokens"
          :saving-option-ids="savingOptionIds"
          :saving-temperature="savingTemperature"
          @save-max-new-tokens="handleMaxNewTokensSave"
          @save-temperature="handleTemperatureSave"
          @toggle-option="handleOptionChange"
          @update:draft-max-new-tokens="updateDraftMaxNewTokens"
          @update:draft-temperature="updateDraftTemperature"
        />
      </div>
    </div>
  </AdminShell>
</template>

<script setup>
import AdminShell from './components/AdminShell.vue'
import EngineOptionsPanel from './components/EngineOptionsPanel.vue'
import { useInferenceOptionsControl } from './useAdminDashboard'

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
  savingTemperature
} = useInferenceOptionsControl()

function updateDraftMaxNewTokens(value) {
  draftMaxNewTokens.value = value
}

function updateDraftTemperature(value) {
  draftTemperature.value = value
}
</script>

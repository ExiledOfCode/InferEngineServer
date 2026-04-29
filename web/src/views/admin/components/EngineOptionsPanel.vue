<!-- 文件说明：引擎参数表单组件，负责选项展示、草稿编辑和保存事件分发。 -->

<template>
  <section class="panel-card panel-card-engine">
    <div class="panel-head">
      <div>
        <h3>引擎优化</h3>
        <p>管理推理进程级别的性能开关与生成参数。</p>
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
          v-model="maxNewTokensModel"
          :min="inferenceOptions.min_max_new_tokens || 16"
          :step="16"
          controls-position="right"
        />
        <el-button
          type="primary"
          :loading="savingMaxNewTokens"
          @click="onSaveMaxNewTokens"
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
          v-model="temperatureModel"
          :min="inferenceOptions.min_temperature ?? 0"
          :max="inferenceOptions.max_temperature ?? 2"
          :step="0.1"
          :precision="2"
          controls-position="right"
        />
        <el-button
          type="primary"
          :loading="savingTemperature"
          @click="onSaveTemperature"
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
          @change="value => onToggleOption(option, value)"
        />
      </article>
    </div>

    <div v-if="!inferenceOptions.options.length" class="empty-hint">
      当前没有可配置的优化项。
    </div>
  </section>
</template>

<script setup>
import { Setting } from '@element-plus/icons-vue'
import { computed } from 'vue'

const props = defineProps({
  currentModelName: {
    type: String,
    required: true
  },
  currentModelSeqLenText: {
    type: String,
    required: true
  },
  draftMaxNewTokens: {
    type: Number,
    required: true
  },
  draftTemperature: {
    type: Number,
    required: true
  },
  inferenceOptions: {
    type: Object,
    required: true
  },
  savingMaxNewTokens: {
    type: Boolean,
    required: true
  },
  savingOptionIds: {
    type: Array,
    required: true
  },
  savingTemperature: {
    type: Boolean,
    required: true
  }
})

const emit = defineEmits([
  'save-max-new-tokens',
  'save-temperature',
  'toggle-option',
  'update:draft-max-new-tokens',
  'update:draft-temperature'
])

const maxNewTokensModel = computed({
  get: () => props.draftMaxNewTokens,
  set: value => emit('update:draft-max-new-tokens', value)
})

const temperatureModel = computed({
  get: () => props.draftTemperature,
  set: value => emit('update:draft-temperature', value)
})

function onSaveMaxNewTokens() {
  emit('save-max-new-tokens')
}

function onSaveTemperature() {
  emit('save-temperature')
}

function onToggleOption(option, value) {
  emit('toggle-option', option, value)
}
</script>

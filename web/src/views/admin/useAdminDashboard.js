import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../../api'

function formatTokenCount(value) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return '未知'
  }
  return Math.round(numeric).toLocaleString()
}

function createInferenceOptionsState() {
  const inferenceOptions = ref({
    current_model_name: '',
    current_model_seq_len: null,
    running: false,
    ready: false,
    trace_enabled: false,
    optimized_weight_loading: false,
    paged_kv_cache: true,
    warmup_on_model_switch: true,
    max_new_tokens: 128,
    default_max_new_tokens: 128,
    min_max_new_tokens: 16,
    max_max_new_tokens: null,
    temperature: 0,
    default_temperature: 0,
    min_temperature: 0,
    max_temperature: 2,
    runtime_options_path: '',
    options: []
  })
  const savingOptionIds = ref([])
  const draftMaxNewTokens = ref(128)
  const savingMaxNewTokens = ref(false)
  const draftTemperature = ref(0)
  const savingTemperature = ref(false)

  const currentModelName = computed(() => inferenceOptions.value.current_model_name || '未选择模型')
  const currentModelSeqLen = computed(() => Number(inferenceOptions.value.current_model_seq_len || 0))
  const currentModelSeqLenText = computed(() => (
    currentModelSeqLen.value > 0 ? `${formatTokenCount(currentModelSeqLen.value)} tokens` : '未知'
  ))

  async function fetchInferenceOptions() {
    try {
      inferenceOptions.value = await adminApi.getInferenceOptions()
      draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || 128)
      draftTemperature.value = Number(inferenceOptions.value.temperature ?? 0)
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
      draftTemperature.value = Number(inferenceOptions.value.temperature ?? draftTemperature.value)
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
      draftTemperature.value = Number(inferenceOptions.value.temperature ?? draftTemperature.value)
      ElMessage.success(`max_token 已更新为 ${inferenceOptions.value.max_new_tokens}`)
    } catch (e) {
      draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || currentValue || 128)
      ElMessage.error(e?.detail || '更新 max_token 失败')
    } finally {
      savingMaxNewTokens.value = false
    }
  }

  async function handleTemperatureSave() {
    const nextValue = Number(draftTemperature.value || 0)
    if (!Number.isFinite(nextValue)) {
      ElMessage.error('temperature 必须是数字')
      return
    }

    const currentValue = Number(inferenceOptions.value.temperature ?? 0)
    if (nextValue === currentValue) {
      return
    }

    savingTemperature.value = true
    try {
      inferenceOptions.value = await adminApi.updateInferenceOptions({
        temperature: nextValue
      })
      draftTemperature.value = Number(inferenceOptions.value.temperature ?? nextValue)
      draftMaxNewTokens.value = Number(inferenceOptions.value.max_new_tokens || draftMaxNewTokens.value)
      ElMessage.success(`temperature 已更新为 ${inferenceOptions.value.temperature}`)
    } catch (e) {
      draftTemperature.value = Number(inferenceOptions.value.temperature ?? currentValue ?? 0)
      ElMessage.error(e?.detail || '更新 temperature 失败')
    } finally {
      savingTemperature.value = false
    }
  }

  return {
    currentModelName,
    currentModelSeqLenText,
    draftMaxNewTokens,
    draftTemperature,
    fetchInferenceOptions,
    handleMaxNewTokensSave,
    handleOptionChange,
    handleTemperatureSave,
    inferenceOptions,
    savingMaxNewTokens,
    savingOptionIds,
    savingTemperature
  }
}

function createOperatorOptionsState() {
  const operatorOptions = ref({
    running: false,
    ready: false,
    runtime_options_path: '',
    groups: []
  })
  const savingOperatorGroupIds = ref([])

  async function fetchOperatorOptions() {
    try {
      operatorOptions.value = await adminApi.getOperatorOptions()
    } catch (e) {
      ElMessage.error(e?.detail || '加载算子优化配置失败')
    }
  }

  async function handleOperatorChange(group, selected) {
    const previous = group.selected
    if (previous === selected) {
      return
    }

    savingOperatorGroupIds.value = [...savingOperatorGroupIds.value, group.id]
    try {
      operatorOptions.value = await adminApi.updateOperatorOptions({
        operators: {
          [group.id]: selected
        }
      })
      const nextGroup = operatorOptions.value.groups.find(item => item.id === group.id)
      ElMessage.success(
        `${group.name}启动版本已切换为${nextGroup?.choices?.find(item => item.id === selected)?.name || selected}`
      )
    } catch (e) {
      group.selected = previous
      ElMessage.error(e?.detail || '更新算子优化项失败')
      await fetchOperatorOptions()
    } finally {
      savingOperatorGroupIds.value = savingOperatorGroupIds.value.filter(id => id !== group.id)
    }
  }

  return {
    fetchOperatorOptions,
    handleOperatorChange,
    operatorOptions,
    savingOperatorGroupIds
  }
}

export function useAdminStats(autoLoad = true) {
  const stats = ref({ user_count: 0, conversation_count: 0, message_count: 0 })

  async function fetchStats() {
    try {
      stats.value = await adminApi.getStats()
    } catch (e) {
      ElMessage.error(e?.detail || '加载统计信息失败')
    }
  }

  if (autoLoad) {
    onMounted(fetchStats)
  }

  return {
    fetchStats,
    stats
  }
}

export function useInferenceOptionsControl(autoLoad = true) {
  const state = createInferenceOptionsState()

  if (autoLoad) {
    onMounted(state.fetchInferenceOptions)
  }

  return state
}

export function useOperatorOptionsControl(autoLoad = true) {
  const state = createOperatorOptionsState()

  if (autoLoad) {
    onMounted(state.fetchOperatorOptions)
  }

  return state
}

export function useAdminDashboard() {
  const statsState = useAdminStats(false)
  const inferenceState = useInferenceOptionsControl(false)
  const operatorState = useOperatorOptionsControl(false)

  onMounted(async () => {
    await Promise.all([
      statsState.fetchStats(),
      inferenceState.fetchInferenceOptions(),
      operatorState.fetchOperatorOptions()
    ])
  })

  return {
    ...statsState,
    ...inferenceState,
    ...operatorState
  }
}

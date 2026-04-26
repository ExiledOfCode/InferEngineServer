<template>
  <section class="panel-card panel-card-operator">
    <div class="panel-head">
      <div>
        <h3>算子优化</h3>
        <p>为每一类算子选择一个启动时实际生效的执行版本，便于观察不同 kernel 的推理表现。</p>
      </div>
      <div class="panel-head-icon panel-head-icon-operator">
        <el-icon><Operation /></el-icon>
      </div>
    </div>

    <div class="runtime-path" v-if="operatorOptions.runtime_options_path">
      <span class="runtime-label">算子配置文件</span>
      <code>{{ operatorOptions.runtime_options_path }}</code>
    </div>

    <div class="operator-group-list">
      <article
        v-for="group in operatorOptions.groups"
        :key="group.id"
        class="operator-group-item"
      >
        <div class="option-meta">
          <div class="option-title-row">
            <span class="option-title">{{ group.name }}</span>
            <span class="option-tag">启动版本: {{ selectedChoiceName(group) }}</span>
            <span v-if="group.requires_restart" class="option-tag">切换后重启生效</span>
          </div>
          <p class="option-desc">{{ group.description || '暂无说明' }}</p>
          <p class="option-desc">
            选择结果会写入运行时配置；如需关闭实验版并回到原始实现，切回 `Kuiper CUDA` 即可。
          </p>
        </div>

        <el-radio-group
          class="operator-choice-list"
          :model-value="group.selected"
          :disabled="savingOperatorGroupIds.includes(group.id)"
          @change="value => onChange(group, value)"
        >
          <label
            v-for="choice in group.choices"
            :key="choice.id"
            class="operator-choice"
            :class="{ disabled: !choice.supported }"
          >
            <el-radio
              :value="choice.id"
              :label="choice.id"
              :disabled="!choice.supported"
            >
              <span class="operator-choice-name">{{ choice.name }}</span>
            </el-radio>
            <p class="operator-choice-desc">
              {{ choice.description || '暂无说明' }}
            </p>
          </label>
        </el-radio-group>
      </article>
    </div>

    <div v-if="!operatorOptions.groups.length" class="empty-hint">
      当前没有可配置的算子优化项。
    </div>
  </section>
</template>

<script setup>
import { Operation } from '@element-plus/icons-vue'

const props = defineProps({
  operatorOptions: {
    type: Object,
    required: true
  },
  savingOperatorGroupIds: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['change'])

function onChange(group, value) {
  emit('change', group, value)
}

function selectedChoiceName(group) {
  return group.choices.find(choice => choice.id === group.selected)?.name || group.selected
}
</script>

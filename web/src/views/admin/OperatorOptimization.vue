<!-- 文件说明：算子优化页面，按算子组选择 CPU/CUDA 实现并提示重启敏感项。 -->

<template>
  <AdminShell active-view="operators">
    <div class="admin-page">
      <header class="admin-page-hero">
        <div>
          <span class="admin-page-kicker">Operators</span>
          <h2 class="admin-page-title">算子优化</h2>
          <p class="admin-page-description">
            每一类算子都单独选择一个启动时生效的实现版本，便于观察不同 CUDA kernel 的行为、性能和稳定性。
          </p>
        </div>

        <div class="admin-page-hero__aside">
          <article class="hero-info-card">
            <div class="hero-info-label">可配置算子组</div>
            <div class="hero-info-value">{{ operatorOptions.groups.length }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">当前状态</div>
            <div class="hero-info-value">{{ operatorOptions.running ? '引擎运行中' : '等待启动' }}</div>
          </article>
          <article class="hero-info-card">
            <div class="hero-info-label">重启要求</div>
            <div class="hero-info-value">{{ restartSensitiveGroupCount }} 项切换后需要重启</div>
          </article>
        </div>
      </header>

      <div class="admin-grid-single">
        <OperatorOptionsPanel
          :operator-options="operatorOptions"
          :saving-operator-group-ids="savingOperatorGroupIds"
          @change="handleOperatorChange"
        />
      </div>
    </div>
  </AdminShell>
</template>

<script setup>
import { computed } from 'vue'

import AdminShell from './components/AdminShell.vue'
import OperatorOptionsPanel from './components/OperatorOptionsPanel.vue'
import { useOperatorOptionsControl } from './useAdminDashboard'

const {
  handleOperatorChange,
  operatorOptions,
  savingOperatorGroupIds
} = useOperatorOptionsControl()

const restartSensitiveGroupCount = computed(
  () => operatorOptions.value.groups.filter(group => group.requires_restart).length
)
</script>

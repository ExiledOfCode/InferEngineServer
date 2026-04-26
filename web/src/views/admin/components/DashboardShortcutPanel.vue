<template>
  <section class="panel-card panel-card-shortcuts">
    <div class="panel-head">
      <div>
        <h3>快捷分区</h3>
        <p>把常用管理能力拆成独立分区，减少在一个页面里堆叠过多控制项。</p>
      </div>
    </div>

    <div class="shortcut-grid">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        class="shortcut-card"
        :to="item.to"
      >
        <div class="shortcut-icon">
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <div>
          <div class="shortcut-title">{{ item.title }}</div>
          <p class="shortcut-desc">{{ item.description }}</p>
        </div>
        <div class="shortcut-meta">{{ item.meta }}</div>
      </RouterLink>
    </div>
  </section>
</template>

<script setup>
import { Operation, Setting, User } from '@element-plus/icons-vue'
import { RouterLink } from 'vue-router'

const items = [
  {
    to: '/admin/users',
    title: '用户管理',
    description: '集中处理账号创建、状态切换、密码重置和用户清理。',
    meta: '进入用户区',
    icon: User
  },
  {
    to: '/admin/engine',
    title: '引擎优化',
    description: '单独维护推理进程、埋点、KV cache、温度和 max_token 等配置。',
    meta: '进入引擎区',
    icon: Setting
  },
  {
    to: '/admin/operators',
    title: '算子优化',
    description: '按算子类别切换 CUDA 实现版本，观察不同 kernel 的推理现象。',
    meta: '进入算子区',
    icon: Operation
  }
]
</script>

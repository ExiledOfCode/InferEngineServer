<!-- 文件说明：登录页面，负责凭据提交和登录后的角色路由跳转。 -->

<template>
  <div class="login-shell">
    <div class="aurora one"></div>
    <div class="aurora two"></div>
    <div class="login-box">
      <div class="brand">
        <div class="logo-mark">AI</div>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageSubtitle }}</p>
      </div>

      <div class="mode-switch" role="tablist" aria-label="账号操作">
        <button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" class="login-form">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" size="large" show-password @keyup.enter="handleSubmit" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" placeholder="确认密码" prefix-icon="Lock" size="large" show-password @keyup.enter="handleSubmit" />
        </el-form-item>
        <el-form-item>
          <el-button class="login-btn" type="primary" size="large" :loading="loading" @click="handleSubmit">{{ actionText }}</el-button>
        </el-form-item>
      </el-form>
      <div class="tips" v-if="mode === 'login'">默认管理员账号：<code>admin / admin</code></div>
      <div class="tips" v-else>注册成功后将以普通用户身份进入聊天页</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)
const mode = ref('login')
const form = reactive({ username: '', password: '', confirmPassword: '' })
const pageTitle = computed(() => mode.value === 'login' ? '欢迎回来' : '创建账号')
const pageSubtitle = computed(() => mode.value === 'login' ? '登录后继续你的智能对话' : '注册后开始你的智能对话')
const actionText = computed(() => mode.value === 'login' ? '登录' : '注册并进入')

function validateUsername(_, value, callback) {
  const username = String(value || '').trim()
  if (!username) {
    callback(new Error('请输入用户名'))
    return
  }
  if (mode.value === 'register' && (username.length < 3 || username.length > 50)) {
    callback(new Error('用户名长度需为 3-50 个字符'))
    return
  }
  if (mode.value === 'register' && /\s/.test(username)) {
    callback(new Error('用户名不能包含空白字符'))
    return
  }
  callback()
}

function validatePassword(_, value, callback) {
  if (!value) {
    callback(new Error('请输入密码'))
    return
  }
  if (mode.value === 'register' && value.length < 6) {
    callback(new Error('密码至少需要 6 位'))
    return
  }
  callback()
}

function validateConfirmPassword(_, value, callback) {
  if (mode.value !== 'register') {
    callback()
    return
  }
  if (!value) {
    callback(new Error('请再次输入密码'))
    return
  }
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const rules = {
  username: [{ validator: validateUsername, trigger: 'blur' }],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  confirmPassword: [{ validator: validateConfirmPassword, trigger: 'blur' }]
}

function switchMode(nextMode) {
  mode.value = nextMode
  form.confirmPassword = ''
  nextTick(() => formRef.value?.clearValidate())
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
    loading.value = true
    const username = form.username.trim()
    const user = mode.value === 'login'
      ? await authStore.login(username, form.password)
      : await authStore.register(username, form.password)
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    router.push(user.role === 'admin' ? '/admin/dashboard' : '/chat')
  } catch (e) {
    if (!e?.detail && !e?.message) {
      return
    }
    if (e?.detail) {
      ElMessage.error(e.detail)
    } else if (e?.message) {
      ElMessage.error(e.message)
    } else {
      ElMessage.error(mode.value === 'login' ? '登录失败' : '注册失败')
    }
  }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(180deg, #edf2f9 0%, #f8fafc 65%, #ffffff 100%);
}

.aurora {
  position: absolute;
  border-radius: 999px;
  filter: blur(36px);
  opacity: 0.45;
  pointer-events: none;
}

.aurora.one {
  width: 280px;
  height: 280px;
  top: -80px;
  right: 15%;
  background: rgba(16, 163, 127, 0.35);
}

.aurora.two {
  width: 320px;
  height: 320px;
  bottom: -120px;
  left: 10%;
  background: rgba(86, 123, 189, 0.35);
}

.login-box {
  width: min(430px, 100%);
  border-radius: 22px;
  border: 1px solid var(--border-subtle);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(6px);
  box-shadow: var(--shadow-float);
  padding: 34px 32px 24px;
  position: relative;
  z-index: 1;
}

.brand {
  text-align: center;
}

.logo-mark {
  width: 54px;
  height: 54px;
  margin: 0 auto 12px;
  border-radius: 16px;
  background: linear-gradient(140deg, #10a37f, #0f7d62);
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand h1 {
  font-size: 30px;
  color: #101828;
  line-height: 1.15;
}

.brand p {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 14px;
}

.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 24px;
  padding: 5px;
  border-radius: 13px;
  background: #eef2f8;
  border: 1px solid #dbe2ec;
}

.mode-switch button {
  height: 36px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 650;
  cursor: pointer;
}

.mode-switch button.active {
  background: #ffffff;
  color: #0f7d62;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.login-form {
  margin-top: 22px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 12px;
  box-shadow: none;
  border: 1px solid var(--border-subtle);
  background: #fbfcfe;
  padding: 4px 12px;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  border-color: #9fc7ba;
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.15);
}

.login-btn {
  width: 100%;
  border-radius: 12px;
  border: none;
  height: 44px;
  font-weight: 650;
  letter-spacing: 0.3px;
  background: linear-gradient(130deg, #10a37f, #0f7d62);
}

.login-btn:hover {
  filter: brightness(1.02);
}

.tips {
  margin-top: 4px;
  color: var(--text-muted);
  text-align: center;
  font-size: 12px;
}

.tips code {
  color: #3b4252;
  background: #eef2f8;
  border: 1px solid #d7ddeb;
  border-radius: 8px;
  padding: 2px 7px;
}
</style>

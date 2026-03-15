<template>
  <div class="login-shell">
    <div class="aurora one"></div>
    <div class="aurora two"></div>
    <div class="login-box">
      <div class="brand">
        <div class="logo-mark">AI</div>
        <h1>欢迎回来</h1>
        <p>登录后继续你的智能对话</p>
      </div>
      <el-form :model="form" :rules="rules" ref="formRef" class="login-form">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" size="large" show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-button class="login-btn" type="primary" size="large" :loading="loading" @click="handleLogin">登录</el-button>
        </el-form-item>
      </el-form>
      <div class="tips">默认管理员账号：<code>admin / admin</code></div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = { username: [{ required: true, message: '请输入用户名', trigger: 'blur' }], password: [{ required: true, message: '请输入密码', trigger: 'blur' }] }

async function handleLogin() {
  try {
    await formRef.value.validate()
    loading.value = true
    const user = await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push(user.role === 'admin' ? '/admin/dashboard' : '/chat')
  } catch (e) { ElMessage.error(e.detail || '登录失败') }
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

.login-form {
  margin-top: 28px;
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

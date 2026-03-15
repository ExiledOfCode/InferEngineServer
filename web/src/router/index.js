import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { guest: true } },
  { path: '/chat', name: 'Chat', component: () => import('../views/Chat.vue'), meta: { requiresAuth: true, role: 'user' } },
  { path: '/admin', redirect: '/admin/dashboard', meta: { requiresAuth: true, role: 'admin' }, children: [
    { path: 'dashboard', name: 'Dashboard', component: () => import('../views/admin/Dashboard.vue') },
    { path: 'users', name: 'Users', component: () => import('../views/admin/Users.vue') }
  ]},
  { path: '/', redirect: '/login' }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isLoggedIn) { next('/login') }
  else if (to.meta.guest && authStore.isLoggedIn) { next(authStore.user?.role === 'admin' ? '/admin/dashboard' : '/chat') }
  else if (to.meta.role && authStore.user?.role !== to.meta.role) { next(authStore.user?.role === 'admin' ? '/admin/dashboard' : '/chat') }
  else { next() }
})

export default router

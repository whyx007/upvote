import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('upvote_token') || '',
    teacher: JSON.parse(localStorage.getItem('upvote_teacher') || 'null')
  }),
  getters: {
    isAdmin: (s) => s.teacher?.role === 'admin',
    loggedIn: (s) => !!s.token
  },
  actions: {
    setLogin(token, teacher) {
      this.token = token
      this.teacher = teacher
      localStorage.setItem('upvote_token', token)
      localStorage.setItem('upvote_teacher', JSON.stringify(teacher))
    },
    logout() {
      this.token = ''
      this.teacher = null
      localStorage.removeItem('upvote_token')
      localStorage.removeItem('upvote_teacher')
    }
  }
})
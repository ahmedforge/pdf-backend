export function readToken() {
  try { return localStorage.getItem('token') || '' } catch { return '' }
}
export function saveToken(token) {
  try { localStorage.setItem('token', token); return true } catch { return false }
}
export function removeToken() {
  try { localStorage.removeItem('token') } catch { /* In-memory logout still succeeds. */ }
}

// UI-only interpretation. The backend independently enforces guest permissions.
export function isGuestToken(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(part)).guest === true
  } catch { return false }
}

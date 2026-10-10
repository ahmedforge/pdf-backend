export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "")

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) {
    const body = await response.text()
    let message = `Request failed (${response.status})`
    try {
      const data = JSON.parse(body)
      if (typeof data.detail === "string") message = data.detail
    } catch { /* Upstream HTML errors should not fill the application UI. */ }
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return response
}

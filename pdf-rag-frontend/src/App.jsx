import { useCallback, useEffect, useRef, useState } from "react"
import { apiRequest } from "./api"
import { useUploadQueue } from "@/hooks/use-upload-queue"
import { readToken, saveToken, removeToken } from "@/lib/token-storage"
import { isGuestToken } from "@/lib/guest-session"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import { useDocumentChat } from "@/hooks/use-document-chat"
import { WorkspaceShell } from "@/components/workspace-shell"

async function fetchFiles(token) {
  const response = await apiRequest("/files", {
    headers: { Authorization: `Bearer ${token}` },
  })
  return response.json()
}

function App() {
  const [authMode, setAuthMode] = useState("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [token, setToken] = useState(readToken)
  const guest = isGuestToken(token)
  const activeToken = useRef(token)
  useEffect(() => { activeToken.current = token }, [token])

  const [files, setFiles] = useState([])
  const [documentId, setDocumentId] = useState(null)

  const chat = useDocumentChat(token)
  const question = chat.drafts[documentId] || ""
  const resetChat = chat.reset
  const [message, setMessage] = useState("")
  const [loading, setLoading] = useState(false)

  const applyFiles = useCallback(data => {
    setFiles(data.files || [])
    setDocumentId(previous => previous ?? data.files?.[0]?.id ?? null)
  }, [])

  const handleFileError = useCallback(error => {
    if (error.status === 401) {
      resetChat()
      removeToken()
      setToken("")
      setFiles([])
      setDocumentId(null)
      setMessage("Your session expired. Please log in again.")
    } else {
      setMessage(`Could not load files: ${error.message}`)
    }
  }, [resetChat])

  const loadFiles = useCallback(() => {
    if (!token) return Promise.resolve()
    return fetchFiles(token)
      .then(data => { if (activeToken.current === token) applyFiles(data) })
      .catch(error => { if (activeToken.current === token) handleFileError(error) })
  }, [token, applyFiles, handleFileError])

  useEffect(() => {
    if (!token) return
    let active = true
    fetchFiles(token)
      .then(data => { if (active) applyFiles(data) })
      .catch(error => { if (active) handleFileError(error) })
    return () => { active = false }
  }, [token, applyFiles, handleFileError])

  async function startGuestDemo() {
    setLoading(true)
    setMessage("Opening the sample PDF… the server may need a moment to wake up.")
    try {
      const response = await apiRequest("/auth/guest", { method: "POST" })
      const data = await response.json()
      chat.reset()
      saveToken(data.access_token)
      setDocumentId(data.document_id)
      setToken(data.access_token)
      setMessage("")
    } catch (error) {
      setMessage(`Could not open the demo: ${error.message}`)
    } finally { setLoading(false) }
  }

  async function handleLogin(event) {
    event.preventDefault()
    setLoading(true)
    setMessage("Connecting… the first request may take about a minute while the server wakes up.")

    try {
      if (authMode === "register") {
        await apiRequest("/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        })
      }
      const response = await apiRequest("/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      })

      const data = await response.json()

      chat.reset()
      const savedToken = saveToken(data.access_token)
      setToken(data.access_token)
      setPassword("")
      setMessage(savedToken ? (authMode === "register" ? "Account created and logged in" : "Login successful") : "Logged in. Device storage is unavailable; sign in again after reloading.")
    } catch (error) {
      setMessage(`Authentication failed: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const uploads = useUploadQueue(token, async data => {
    setDocumentId(previous => previous ?? data.document_id)
    await loadFiles()
  })

  async function renameDocument(id, displayName) {
    const previous = files.find(file => file.id === id)
    setFiles(old => old.map(file => file.id === id ? { ...file, display_name: displayName } : file))
    try {
      const response = await apiRequest(`/files/${id}`, { method: 'PATCH', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName }) })
      const updated = await response.json()
      setFiles(old => old.map(file => file.id === id ? updated : file))
    } catch (error) {
      setFiles(old => old.map(file => file.id === id ? previous : file))
      throw error
    }
  }

  async function deleteDocument(id) {
    await apiRequest(`/files/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    chat.remove(id)
    setFiles(old => old.filter(file => file.id !== id))
    setDocumentId(old => old === id ? files.find(file => file.id !== id)?.id ?? null : old)
    setMessage('Document deleted.')
  }

  function handleAsk(event) {
    event.preventDefault()
    setMessage(""); chat.send(documentId, question)
  }

  function selectDocument(id) {
    if (id !== documentId) chat.stop()
    setDocumentId(id)
    setMessage("")
  }

  function handleLogout() {
    uploads.reset()
    removeToken()
    setToken("")
    setFiles([])
    setDocumentId(null)
    chat.reset()
    setMessage("")
  }

  if (!token) {
    return (
      <div style={{ maxWidth: "420px", margin: "80px auto", padding: "24px" }}>
        <div className="flex justify-end"><ThemeToggle /></div>
        <h1>PDF RAG</h1>
        <p className="my-3 text-sm text-muted-foreground">Ask a question and jump to the supporting passage in a PDF.</p>
        <Button className="my-3 w-full rounded-xl" onClick={startGuestDemo} disabled={loading}>Try the demo — no signup</Button>
        <p className="mb-6 text-sm text-muted-foreground">Explore a sample PDF, chat and page citations. Sign in below to upload your own documents.</p>
        <h2>{authMode === "register" ? "Create account" : "Login"}</h2>

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: "16px" }}>
            <label>Email</label>
            <br />
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              style={{ width: "100%", padding: "10px", marginTop: "6px" }}
            />
          </div>

          <div style={{ marginBottom: "16px" }}>
            <label>Password</label>
            <br />
            <input
              type="password"
              minLength={authMode === "register" ? 8 : undefined}
              maxLength={128}
              autoComplete={authMode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              style={{ width: "100%", padding: "10px", marginTop: "6px" }}
            />
          </div>

          <button type="submit" disabled={loading}>
            {loading ? "Please wait…" : authMode === "register" ? "Create account" : "Login"}
          </button>
        </form>
        <button type="button" disabled={loading} onClick={() => {
          setAuthMode(previous => previous === "login" ? "register" : "login")
          setMessage("")
        }}>
          {authMode === "login" ? "New here? Create an account" : "Already have an account? Login"}
        </button>

        <p>{message}</p>
      </div>
    )
  }

  return (
    <WorkspaceShell
      token={token} guest={guest} files={files} documentId={documentId}
      onSelectDocument={selectDocument} onUpload={uploads.add} uploads={uploads} onRename={renameDocument} onDelete={deleteDocument}
      onLogout={handleLogout} question={question} onQuestionChange={text => chat.setDraft(documentId, text)}
      onAsk={handleAsk} turns={chat.conversations[documentId] || []}
      generating={Boolean(documentId) && chat.activeDocument === documentId} onStop={chat.stop}
      onRetry={turn => chat.send(documentId, turn.question, turn.id)}
      onClear={() => chat.clear(documentId)} storageWarning={chat.storageWarning} message={message} loading={false}
    />
  )
}

export default App

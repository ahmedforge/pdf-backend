import { useCallback, useEffect, useState } from "react"
import { apiRequest } from "./api"

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
  const [token, setToken] = useState(localStorage.getItem("token") || "")

  const [files, setFiles] = useState([])
  const [file, setFile] = useState(null)
  const [documentId, setDocumentId] = useState(null)

  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState("")
  const [message, setMessage] = useState("")
  const [loading, setLoading] = useState(false)

  const applyFiles = useCallback(data => {
    setFiles(data.files || [])
    setDocumentId(previous => previous ?? data.files?.[0]?.id ?? null)
  }, [])

  const handleFileError = useCallback(error => {
    if (error.status === 401) {
      localStorage.removeItem("token")
      setToken("")
      setFiles([])
      setDocumentId(null)
      setMessage("Your session expired. Please log in again.")
    } else {
      setMessage(`Could not load files: ${error.message}`)
    }
  }, [])

  const loadFiles = useCallback(() => {
    if (!token) return Promise.resolve()
    return fetchFiles(token).then(applyFiles).catch(handleFileError)
  }, [token, applyFiles, handleFileError])

  useEffect(() => {
    if (!token) return
    let active = true
    fetchFiles(token)
      .then(data => { if (active) applyFiles(data) })
      .catch(error => { if (active) handleFileError(error) })
    return () => { active = false }
  }, [token, applyFiles, handleFileError])

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

      localStorage.setItem("token", data.access_token)
      setToken(data.access_token)
      setPassword("")
      setMessage(authMode === "register" ? "Account created and logged in" : "Login successful")
    } catch (error) {
      setMessage(`Authentication failed: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload() {
    if (!file) {
      setMessage("Choose a PDF first")
      return
    }

    setLoading(true)
    setMessage("Uploading and indexing… the first PDF may take several minutes.")

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await apiRequest("/upload", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })

      const data = await response.json()

      setDocumentId(data.document_id)
      setMessage(`Uploaded successfully. Document ID: ${data.document_id}`)

      await loadFiles()
    } catch (error) {
      setMessage(`Upload failed: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleAsk(event) {
    event.preventDefault()

    if (!documentId) {
      setMessage("Select or upload a PDF first")
      return
    }

    if (!question.trim()) {
      return
    }

    setAnswer("")
    setLoading(true)
    setMessage("Generating answer...")

    try {
      const response = await apiRequest(
        `/files/${documentId}/ask/stream`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question,
            top_k: 3,
          }),
        }
      )

      if (!response.body) throw new Error("No answer stream was received")
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let received = ""

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        const chunk = decoder.decode(value, {
          stream: true,
        })

        received += chunk
        setAnswer(received)
      }
      received += decoder.decode()
      setAnswer(received)
      setMessage(received.includes("[Generation interrupted.") ? "Generation was interrupted. Please retry." : "Answer complete")
    } catch (error) {
      setMessage(`Question failed: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  function handleLogout() {
    localStorage.removeItem("token")
    setToken("")
    setFiles([])
    setDocumentId(null)
    setAnswer("")
    setMessage("")
  }

  if (!token) {
    return (
      <div style={{ maxWidth: "420px", margin: "80px auto", padding: "24px" }}>
        <h1>PDF RAG</h1>
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
    <div style={{ maxWidth: "800px", margin: "40px auto", padding: "24px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <h1>PDF RAG</h1>
        <button onClick={handleLogout}>Logout</button>
      </div>

      <hr />

      <h2>1. Select Existing PDF</h2>

      {files.length > 0 ? (
        <select
          value={documentId || ""}
          onChange={(event) => setDocumentId(Number(event.target.value))}
          style={{ width: "100%", padding: "10px" }}
        >
          {files.map((item) => (
            <option key={item.id} value={item.id}>
              {item.filename} (ID: {item.id})
            </option>
          ))}
        </select>
      ) : (
        <p>No existing PDFs found.</p>
      )}

      <hr />

      <h2>2. Upload New PDF</h2>

      <input
        type="file"
        accept="application/pdf"
        onChange={(event) => setFile(event.target.files[0])}
      />

      <br />
      <br />

      <button onClick={handleUpload} disabled={loading}>
        Upload PDF
      </button>

      {documentId && (
        <p>
          Selected Document ID: <strong>{documentId}</strong>
        </p>
      )}

      <hr />

      <h2>3. Ask your PDF</h2>

      <form onSubmit={handleAsk}>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the PDF..."
          rows="4"
          style={{
            width: "100%",
            padding: "12px",
          }}
        />

        <br />
        <br />

        <button type="submit" disabled={loading || !documentId}>
          Ask
        </button>
      </form>

      <h2>Answer</h2>

      <div
        style={{
          minHeight: "150px",
          whiteSpace: "pre-wrap",
          border: "1px solid #555",
          padding: "16px",
          borderRadius: "8px",
        }}
      >
        {answer || "The streamed answer will appear here."}
      </div>

      <p>{message}</p>
    </div>
  )
}

export default App

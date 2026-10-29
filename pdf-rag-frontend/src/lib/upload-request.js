import { uploadError } from './upload-state.js'
export function uploadPdf(baseUrl, token, file, { onProgress, onProcessing, xhrFactory = () => new XMLHttpRequest() }) {
  const xhr = xhrFactory()
  let processing = false
  const promise = new Promise((resolve, reject) => {
    const fail = (kind, status = xhr.status) => {
      const failureKind = kind === 'http' && status === 504 ? 'timeout' : kind
      const error = new Error(uploadError(status, xhr.responseText, failureKind))
      Object.assign(error, { kind: failureKind, status, sent: processing })
      reject(error)
    }
    xhr.open('POST', `${baseUrl}/upload`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    // Synchronous ingestion can take several minutes. A bounded timeout permits reconciliation.
    xhr.timeout = 15 * 60 * 1000
    const sent = () => { if (!processing) { processing = true; onProcessing() } }
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return
      onProgress(Math.min(100, Math.floor(event.loaded / event.total * 100)))
      if (event.loaded >= event.total) sent()
    }
    xhr.upload.onload = sent
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) { fail('http'); return }
      try {
        const result = JSON.parse(xhr.responseText)
        if (!Number.isInteger(result.document_id)) throw new Error('Invalid upload response')
        resolve(result)
      } catch { fail('response') }
    }
    xhr.onerror = () => fail('network')
    xhr.ontimeout = () => fail('timeout')
    xhr.onabort = () => fail('abort')
    const body = new FormData(); body.append('file', file)
    xhr.send(body)
  })
  return { promise, cancel: () => { if (processing) return false; xhr.abort(); return true }, dispose: () => xhr.abort() }
}

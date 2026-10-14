import test from 'node:test'
import assert from 'node:assert/strict'
import { queueReducer, validatePdf, MAX_PDF_BYTES, uploadError, reconcileUpload, shouldReconcileUpload } from '../src/lib/upload-state.js'
import { uploadPdf } from '../src/lib/upload-request.js'

test('PDF validation permits exact 10 MiB and rejects larger/type/extension mismatches', () => {
  const file = { name: 'REPORT.PDF', type: 'application/pdf', size: MAX_PDF_BYTES }
  assert.equal(validatePdf(file), '')
  assert.match(validatePdf({ ...file, size: MAX_PDF_BYTES + 1 }), /10 MiB/)
  assert.match(validatePdf({ ...file, type: 'text/plain' }), /PDF/)
  assert.match(validatePdf({ ...file, name: 'report.txt' }), /PDF/)
})
test('server detail strings/arrays and friendly status errors never become object strings or HTML', () => {
  assert.equal(uploadError(422, { detail: [{ msg: 'Unreadable PDF' }, { msg: 'Missing text' }] }), 'Unreadable PDF; Missing text')
  assert.equal(uploadError(422, '{"detail":"Encrypted PDF"}'), 'Encrypted PDF')
  assert.doesNotMatch(uploadError(422, { detail: [{}] }), /object Object/)
  assert.match(uploadError(409, ''), /already uploaded/)
  assert.match(uploadError(413, ''), /10485760/)
  assert.match(uploadError(503, ''), /temporarily unavailable/)
  assert.match(uploadError(500, '<html>secret</html>'), /Upload failed/)
  assert.match(uploadError(0, '', 'network'), /Connection lost/)
  assert.match(uploadError(0, '', 'timeout'), /timed out/)
})
test('queue state machine preserves per-file status; processing cannot be cancelled/dismissed', () => {
  let state = queueReducer([], { type: 'add', items: [{ id: 'a', status: 'queued', progress: 0 }, { id: 'b', status: 'queued', progress: 0 }] })
  state = queueReducer(state, { type: 'start', id: 'a' })
  state = queueReducer(state, { type: 'progress', id: 'a', progress: 73 })
  state = queueReducer(state, { type: 'progress', id: 'a', progress: 22 })
  assert.equal(state[0].progress, 73)
  assert.equal(state[1].status, 'queued')
  assert.equal(queueReducer(state, { type: 'start', id: 'b' })[1].status, 'queued')
  state = queueReducer(state, { type: 'processing', id: 'a' })
  assert.equal(state[0].progress, 100)
  assert.equal(queueReducer(state, { type: 'cancel', id: 'a' })[0].status, 'processing')
  assert.equal(queueReducer(state, { type: 'dismiss', id: 'a' }).length, 2)
  state = queueReducer(state, { type: 'ready', id: 'a', documentId: 10 })
  state = queueReducer(state, { type: 'start', id: 'b' })
  state = queueReducer(state, { type: 'cancel', id: 'b' })
  assert.equal(state[0].status, 'ready')
  state = queueReducer(state, { type: 'retry', id: 'b' })
  assert.equal(state[1].status, 'queued')
  assert.equal(queueReducer(state, { type: 'start', id: 'b' })[1].status, 'uploading')
  state = queueReducer(state, { type: 'fail', id: 'b', error: 'Offline' })
  assert.equal(state[1].error, 'Offline')
  assert.equal(queueReducer(state, { type: 'dismiss', id: 'b' }).length, 1)
})
test('lost-response reconciliation requires a new id, original filename and matching size', () => {
  const file = { name: 'report.pdf', size: 100 }
  const previous = [{ id: 1, filename: file.name, size_bytes: 100 }]
  assert.equal(reconcileUpload(previous, previous, file), undefined)
  const recovered = { id: 2, filename: file.name, size_bytes: 100 }
  assert.equal(reconcileUpload(previous, [...previous, recovered], file), recovered)
  assert.equal(reconcileUpload(previous, [{ ...recovered, size_bytes: 101 }], file), undefined)
})
function fakeXhr() {
  return { upload: {}, status: 200, responseText: '{"document_id":12}', headers: {},
    open(method, url) { this.method = method; this.url = url },
    setRequestHeader(name, value) { this.headers[name] = value },
    send(body) { this.body = body }, abort() { this.onabort() } }
}
const file = new Blob(['pdf'], { type: 'application/pdf' })
test('XHR reports real progress, enters Processing at full body send and rejects cancellation after it', async () => {
  const xhr = fakeXhr(), progress = []; let processing = 0
  const request = uploadPdf('http://localhost:8000', 'token', file, { xhrFactory: () => xhr, onProgress: value => progress.push(value), onProcessing: () => processing++ })
  assert.equal(xhr.url, 'http://localhost:8000/upload')
  assert.equal(xhr.headers.Authorization, 'Bearer token')
  xhr.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 })
  assert.deepEqual(progress, [50]); assert.equal(processing, 0)
  xhr.upload.onprogress({ lengthComputable: true, loaded: 10, total: 10 }); xhr.upload.onload()
  assert.equal(processing, 1); assert.equal(request.cancel(), false)
  xhr.onload(); assert.equal((await request.promise).document_id, 12)
})
test('XHR network failures retain sent flag for reconciliation; abort works only before Processing', async () => {
  const xhr = fakeXhr()
  const request = uploadPdf('', 't', file, { xhrFactory: () => xhr, onProgress() {}, onProcessing() {} })
  xhr.upload.onload(); xhr.onerror()
  await assert.rejects(request.promise, error => error.kind === 'network' && error.sent)
  const xhr2 = fakeXhr()
  const cancelled = uploadPdf('', 't', file, { xhrFactory: () => xhr2, onProgress() {}, onProcessing() {} })
  assert.equal(cancelled.cancel(), true)
  await assert.rejects(cancelled.promise, error => error.kind === 'abort' && !error.sent)
})

test('only body-sent network/timeout or browser-retry conflicts trigger reconciliation', () => {
  assert.equal(shouldReconcileUpload({ sent: true, kind: 'network' }), true)
  assert.equal(shouldReconcileUpload({ sent: true, kind: 'timeout' }), true)
  assert.equal(shouldReconcileUpload({ sent: true, kind: 'http', status: 409 }), true)
  assert.equal(shouldReconcileUpload({ sent: false, kind: 'network' }), false)
  assert.equal(shouldReconcileUpload({ sent: true, kind: 'http', status: 422 }), false)
})

test('HTTP gateway timeout after body send uses timeout reconciliation', async () => {
  const xhr = fakeXhr()
  const request = uploadPdf('', 't', file, { xhrFactory: () => xhr, onProgress() {}, onProcessing() {} })
  xhr.upload.onload(); xhr.status = 504; xhr.responseText = '<html>Gateway timeout</html>'; xhr.onload()
  await assert.rejects(request.promise, error => error.kind === 'timeout' && error.sent && shouldReconcileUpload(error))
})

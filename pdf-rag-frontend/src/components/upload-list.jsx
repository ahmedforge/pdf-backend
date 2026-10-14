import { Button } from '@/components/ui/button'
export function UploadList({ uploads }) {
  if (!uploads.items.length) return null
  return <section aria-label="Upload queue" className="max-h-64 space-y-2 overflow-y-auto border-t px-3 py-3">
    <h3 className="text-xs font-medium text-muted-foreground">Uploads · one at a time</h3>
    {uploads.items.map(item => <div key={item.id} className="fade-in rounded-xl border bg-background p-3 text-xs">
      <p className="truncate font-medium" title={item.file.name}>{item.file.name}</p>
      <p role="status" className="mt-2 text-muted-foreground">{({ queued: 'Queued', uploading: `Uploading · ${item.progress}%`, processing: 'Processing…', ready: 'Ready', cancelled: 'Cancelled', failed: 'Failed' })[item.status]}</p>
      {item.status === 'uploading' && <progress aria-label={`Upload progress for ${item.file.name}`} className="mt-2 h-1 w-full accent-primary" value={item.progress} max="100" />}
      {item.status === 'processing' && <p className="mt-2 text-muted-foreground">This can't be cancelled; it will appear when finished.</p>}
      {item.error && <p role="alert" className="mt-2 break-words">{item.error}</p>}
      <div className="mt-1 flex gap-1">
        {item.status === 'uploading' && <Button size="sm" variant="ghost" onClick={() => uploads.cancel(item.id)}>Cancel</Button>}
        {['failed', 'cancelled'].includes(item.status) && <Button size="sm" variant="ghost" onClick={() => uploads.retry(item)}>Retry</Button>}
        {['failed', 'cancelled', 'ready', 'queued'].includes(item.status) && <Button size="sm" variant="ghost" onClick={() => uploads.dismiss(item.id)}>Dismiss</Button>}
      </div>
    </div>)}
  </section>
}

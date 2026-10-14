import { useRef, useState } from 'react'
import { FileText, Pencil, Trash2 } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { Button } from '@/components/ui/button'
export function DocumentItem({ file, selected, onSelect, onRename, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState(false)
  const saving = useRef(false)
  async function rename() {
    if (saving.current) return
    const cleaned = name.replace(/[\p{Cc}\p{Cf}]/gu, '').trim()
    if (!cleaned || [...cleaned].length > 120) { setError('Use a name between 1 and 120 characters.'); return }
    saving.current = true; setBusy(true); setError(''); setEditing(false)
    try { await onRename(file.id, cleaned) } catch (error) { setError(`Rename failed: ${error.message}`); setEditing(true) }
    finally { saving.current = false; setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError('')
    try { await onDelete(file.id); setConfirm(false) }
    catch (error) { setError(`Delete failed: ${error.message}`) }
    finally { setBusy(false) }
  }
  return <div className={`rounded-xl ${selected ? 'bg-accent' : ''}`}>
    <div className="flex items-center">
      {editing ? <input autoFocus aria-label="Document display name" className="m-2 min-w-0 flex-1 rounded-lg border bg-background p-2 text-sm" value={name} disabled={busy} onChange={event => setName(event.target.value)} onKeyDown={event => {
        if (event.key === 'Enter') { event.preventDefault(); rename() }
        if (event.key === 'Escape') { setEditing(false); setError('') }
      }} /> : <Button variant="ghost" className="h-auto min-w-0 flex-1 justify-start px-3 py-3 text-left" aria-current={selected ? 'true' : undefined} title={file.display_name || file.filename} onClick={onSelect}><FileText className="size-4 shrink-0" /><span className="truncate">{file.display_name || file.filename}</span></Button>}
      {!editing && <Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label={`Rename ${file.display_name || file.filename}`} disabled={busy} onClick={() => { setName(file.display_name || file.filename); setError(''); setEditing(true) }}><Pencil className="size-3" /></Button>}
      <Dialog.Root open={confirm} onOpenChange={value => { if (!busy) setConfirm(value) }}>
        <Dialog.Trigger asChild><Button variant="ghost" size="icon" className="mr-1 size-7 shrink-0" disabled={busy} aria-label={`Delete ${file.display_name || file.filename}`}><Trash2 className="size-3" /></Button></Dialog.Trigger>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" /><Dialog.Content className="fade-in fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card p-6 shadow-sm">
          <Dialog.Title className="text-lg font-semibold">Delete this document?</Dialog.Title><Dialog.Description className="mt-2 text-sm text-muted-foreground">{file.display_name || file.filename} and its saved chat will be removed. This cannot be undone.</Dialog.Description>
          {error && <p role="alert" className="mt-3 text-sm">{error}</p>}
          <div className="mt-5 flex justify-end gap-2"><Dialog.Close asChild><Button variant="outline" disabled={busy}>Cancel</Button></Dialog.Close><Button variant="destructive" disabled={busy} onClick={remove}>{busy ? 'Deleting…' : 'Delete document'}</Button></div>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
    {error && !confirm && <p role="alert" className="px-3 pb-2 text-xs">{error}</p>}
    {editing && <p className="px-3 pb-2 text-xs text-muted-foreground">Enter to save · Esc to cancel</p>}
  </div>
}

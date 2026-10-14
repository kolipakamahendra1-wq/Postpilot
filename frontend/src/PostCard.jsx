import { useState } from 'react'
import { CaretDown, Check, X } from '@phosphor-icons/react'
import { decide } from './api'
import { Button, ErrorNote, ICON, StatusChip, fmtWhen, inputCls } from './ui'

const PLATFORM = { x: 'X', linkedin: 'LinkedIn' }

export function Trace({ steps }) {
  return (
    <ol className="divide-y divide-line border-y border-line text-sm">
      {steps.map((s, i) => (
        <li key={i} className="grid grid-cols-[6rem_1fr] gap-3 py-2">
          <span className="font-mono text-xs text-muted">{s.step}</span>
          <span>
            {s.detail}
            {s.planner && <span className="text-muted"> (tools chosen by {s.planner})</span>}
            {s.calls?.map((c, j) => (
              <span key={j} className="mt-1 block font-mono text-xs text-muted">
                {c.tool}: {c.error ? `failed, ${c.error}` : 'ok'}
              </span>
            ))}
            {s.violations?.map((v, j) => (
              <span key={j} className="mt-1 block text-xs text-stamp">{v.message}</span>
            ))}
          </span>
        </li>
      ))}
    </ol>
  )
}

export default function PostCard({ post, onChange }) {
  const [text, setText] = useState(post.draft)
  const [when, setWhen] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const pending = post.status === 'pending_approval'
  const edited = text !== post.draft
  const limit = post.rule_report?.limit

  async function act(action) {
    setBusy(action); setError('')
    try {
      const body = { action: action === 'approve' && edited ? 'edit' : action }
      if (body.action === 'edit') body.text = text
      if (when && action !== 'reject') body.scheduled_at = new Date(when).toISOString()
      onChange(await decide(post.id, body))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <article className="border-t border-ink py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-3 text-sm">
          <span className="font-mono text-muted">#{post.id}</span>
          <span className="font-medium">{PLATFORM[post.platform]}</span>
          <StatusChip status={post.status} />
        </p>
        {post.scheduled_at && post.status !== 'rejected' && <p className="text-xs text-muted">{post.status === 'published' ? 'Published' : 'Goes out'} {fmtWhen(post.published_at || post.scheduled_at)}</p>}
      </div>
      <p className="mt-2 text-sm text-muted">Brief: {post.brief}</p>

      {pending ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_16rem]">
          <div className="flex flex-col gap-2">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} aria-label="Draft text" className={`${inputCls} text-base leading-relaxed`} />
            <p className="flex justify-between text-xs text-muted">
              <span>{edited ? 'Edited by you, rules re-checked on approval.' : 'Written by the agent.'}</span>
              {limit && <span className="font-mono">{text.length} / {limit}</span>}
            </p>
          </div>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium">Publish at</span>
              <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className={inputCls} />
              <span className="text-xs text-muted">Leave empty to publish on the next run.</span>
            </label>
            <div className="flex gap-2">
              <Button variant="stamp" disabled={!!busy} onClick={() => act('approve')} className="flex-1"><Check {...ICON} />{busy === 'approve' ? 'Approving' : edited ? 'Approve edit' : 'Approve'}</Button>
              <Button variant="ghost" disabled={!!busy} onClick={() => act('reject')}><X {...ICON} />Reject</Button>
            </div>
          </div>
        </div>
      ) : (
        <p className="mt-4 max-w-[65ch] whitespace-pre-wrap text-base leading-relaxed">{post.draft}</p>
      )}

      {post.rule_report?.violations?.length > 0 && (
        <ul className="mt-3 text-sm text-stamp">
          {post.rule_report.violations.map((v, i) => <li key={i}>Rule flag: {v.message}</li>)}
        </ul>
      )}
      {post.error && <div className="mt-3"><ErrorNote>{post.error}</ErrorNote></div>}
      {post.publish_ref && <p className="mt-3 font-mono text-xs text-muted">ref {post.publish_ref}</p>}
      <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>

      <button onClick={() => setOpen(!open)} aria-expanded={open} className="mt-4 flex items-center gap-1 text-sm text-muted hover:text-ink">
        <CaretDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} /> Agent run
      </button>
      {open && <div className="mt-2"><Trace steps={post.trace || []} /></div>}
    </article>
  )
}

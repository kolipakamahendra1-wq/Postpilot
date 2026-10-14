import { useCallback, useEffect, useState } from 'react'
import { Warning } from '@phosphor-icons/react'

export const ICON = { weight: 'regular', size: 18 }

const BTN = {
  primary: 'bg-ink text-white hover:bg-black/90 border border-ink',
  stamp: 'bg-stamp text-white hover:bg-[#b02c16] border border-stamp',
  ghost: 'bg-transparent text-ink border border-line hover:border-ink',
}

export function Button({ variant = 'primary', className = '', ...props }) {
  return (
    <button
      {...props}
      className={`btn inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium ${BTN[variant]} ${className}`}
    />
  )
}

const STATUS = {
  pending_approval: ['Needs approval', 'border-stamp text-stamp bg-stamp-soft'],
  scheduled: ['Scheduled', 'border-ink text-ink bg-transparent'],
  published: ['Published', 'border-ink bg-ink text-white'],
  rejected: ['Rejected', 'border-line text-muted bg-transparent'],
  failed: ['Failed', 'border-stamp bg-stamp text-white'],
  drafting: ['Drafting', 'border-line text-muted'],
  deciding: ['Deciding', 'border-line text-muted'],
  publishing: ['Publishing', 'border-ink text-ink'],
}

export function StatusChip({ status }) {
  const [label, tone] = STATUS[status] || [status, 'border-line text-muted']
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone}`}>{label}</span>
}

export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />
}

export function ErrorNote({ children }) {
  if (!children) return null
  return (
    <p role="alert" className="flex items-start gap-2 border-l-2 border-stamp bg-stamp-soft px-3 py-2 text-sm text-stamp">
      <Warning {...ICON} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

export function Empty({ title, children, action }) {
  return (
    <div className="border-t border-line py-14">
      <p className="text-lg font-medium tracking-tight">{title}</p>
      <p className="mt-2 max-w-[52ch] text-muted">{children}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="flex flex-col gap-2 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  )
}

export const inputCls =
  'w-full rounded-md border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted/70 focus:border-ink focus:outline-none'

export function PageHead({ title, children }) {
  return (
    <header className="mb-10 max-w-[60ch]">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {children && <p className="mt-3 text-muted">{children}</p>}
    </header>
  )
}

export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    try {
      setState({ loading: false, data: await fn(), error: '' })
    } catch (e) {
      setState({ loading: false, data: null, error: e.message })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}

export function fmtWhen(iso) {
  if (!iso) return 'next publisher run'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

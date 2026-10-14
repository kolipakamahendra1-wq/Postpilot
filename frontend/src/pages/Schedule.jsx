import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, Plus, Trash } from '@phosphor-icons/react'
import { addCampaign, deleteCampaign, listCampaigns, listPosts, runCampaign } from '../api'
import { Button, Empty, ErrorNote, Field, ICON, PageHead, Skeleton, fmtWhen, inputCls, useAsync } from '../ui'

const PRESETS = [
  ['0 9 * * 1', 'Mondays at 09:00'],
  ['0 9 * * 1-5', 'Weekdays at 09:00'],
  ['0 17 * * *', 'Every day at 17:00'],
  ['*/5 * * * *', 'Every 5 minutes (demo)'],
]

export default function Schedule() {
  const camps = useAsync(listCampaigns)
  const queued = useAsync(() => listPosts('scheduled'))
  const [form, setForm] = useState({ name: '', brief: '', platform: 'x', cron: PRESETS[0][0] })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function guarded(key, fn) {
    setBusy(key); setError('')
    try { await fn(); camps.reload(); queued.reload() } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  return (
    <div>
      <PageHead title="Schedule">
        Cron campaigns write a fresh draft on a timetable. They never publish: every draft still waits in Approvals.
      </PageHead>
      <div className="grid gap-12 lg:grid-cols-[22rem_1fr]">
        <form onSubmit={(e) => { e.preventDefault(); guarded('add', async () => { await addCampaign(form); setForm({ ...form, name: '', brief: '' }) }) }} className="flex flex-col gap-5">
          <Field label="Campaign name"><input required value={form.name} onChange={set('name')} placeholder="Weekly changelog" className={inputCls} /></Field>
          <Field label="Brief" hint="The agent drafts a new post from this brief each time the cron fires.">
            <textarea required minLength={3} rows={3} value={form.brief} onChange={set('brief')} placeholder="Share one practical tip about running local LLM agents." className={inputCls} />
          </Field>
          <Field label="Platform">
            <select value={form.platform} onChange={set('platform')} className={inputCls}><option value="x">X</option><option value="linkedin">LinkedIn</option></select>
          </Field>
          <Field label="When" hint="Standard five field cron, in UTC. Pick a preset or type your own.">
            <input list="presets" value={form.cron} onChange={set('cron')} className={`${inputCls} font-mono`} />
            <datalist id="presets">{PRESETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</datalist>
          </Field>
          <Button type="submit" disabled={busy === 'add'}><Plus {...ICON} />{busy === 'add' ? 'Adding' : 'Add campaign'}</Button>
          <ErrorNote>{error || camps.error}</ErrorNote>
        </form>

        <div className="flex flex-col gap-12">
          <section>
            <h2 className="mb-4 text-lg font-medium tracking-tight">Campaigns</h2>
            {camps.loading && <Skeleton className="h-16 w-full" />}
            {!camps.loading && camps.data?.length === 0 && <Empty title="No campaigns yet">Add one on the left. Use the every 5 minutes preset to watch cron produce a draft.</Empty>}
            {camps.data?.length > 0 && <ul className="divide-y divide-line border-y border-line">
              {camps.data.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
                  <div className="min-w-0">
                    <p className="font-medium">{c.name} <span className="ml-2 font-mono text-xs text-muted">{c.cron}</span></p>
                    <p className="truncate text-sm text-muted">{c.platform === 'x' ? 'X' : 'LinkedIn'}: {c.brief}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" disabled={busy === `run${c.id}`} onClick={() => guarded(`run${c.id}`, () => runCampaign(c.id))}><Play {...ICON} />{busy === `run${c.id}` ? 'Drafting' : 'Run now'}</Button>
                    <Button variant="ghost" aria-label={`Delete ${c.name}`} onClick={() => guarded(`del${c.id}`, () => deleteCampaign(c.id))}><Trash {...ICON} /></Button>
                  </div>
                </li>
              ))}
            </ul>}
          </section>

          <section>
            <h2 className="mb-4 text-lg font-medium tracking-tight">Approved and waiting</h2>
            {queued.loading && <Skeleton className="h-12 w-full" />}
            {!queued.loading && queued.data?.length === 0 && <Empty title="Nothing scheduled">Approve a draft in <Link to="/queue" className="underline">Approvals</Link> and its publish time shows here.</Empty>}
            {queued.data?.length > 0 && <ul className="divide-y divide-line border-y border-line">
              {queued.data.map((p) => (
                <li key={p.id} className="grid grid-cols-[9rem_1fr] gap-4 py-3 text-sm">
                  <span className="font-mono text-muted">{fmtWhen(p.scheduled_at)}</span>
                  <span className="truncate">{p.draft}</span>
                </li>
              ))}
            </ul>}
          </section>
        </div>
      </div>
    </div>
  )
}

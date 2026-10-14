import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play } from '@phosphor-icons/react'
import { listPosts, tick } from '../api'
import PostCard from '../PostCard'
import { Button, Empty, ErrorNote, ICON, PageHead, Skeleton, useAsync } from '../ui'

const TABS = [
  ['pending_approval', 'Needs approval'],
  ['scheduled', 'Scheduled'],
  ['published', 'Published'],
  ['rejected', 'Rejected'],
  ['failed', 'Failed'],
]

export default function Queue() {
  const [tab, setTab] = useState('pending_approval')
  const { loading, data, error, reload } = useAsync(() => listPosts(tab), [tab])
  const [ticking, setTicking] = useState(false)
  const [tickError, setTickError] = useState('')

  async function runPublisher() {
    setTicking(true); setTickError('')
    try { await tick(); await reload() } catch (e) { setTickError(e.message) } finally { setTicking(false) }
  }

  return (
    <div>
      <PageHead title="Approvals">
        Every draft stops here. Edit it, pick a time, then approve or reject. Slack buttons do the same thing.
      </PageHead>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div role="tablist" className="flex gap-5 overflow-x-auto text-sm">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`whitespace-nowrap py-1 ${tab === id ? 'font-medium underline decoration-stamp decoration-2 underline-offset-8' : 'text-muted hover:text-ink'}`}>
              {label}
            </button>
          ))}
        </div>
        <Button variant="ghost" onClick={runPublisher} disabled={ticking}><Play {...ICON} />{ticking ? 'Publishing' : 'Run publisher now'}</Button>
      </div>
      <ErrorNote>{tickError || error}</ErrorNote>

      {loading && <div className="flex flex-col gap-3 border-t border-ink pt-6"><Skeleton className="h-5 w-1/3" /><Skeleton className="h-20 w-full" /></div>}
      {!loading && !error && data?.length === 0 && (
        <Empty title={tab === 'pending_approval' ? 'No drafts waiting' : 'Nothing here yet'}
          action={tab === 'pending_approval' && <Link to="/studio" className="text-sm font-medium text-ink underline">Draft a post in Studio</Link>}>
          {tab === 'pending_approval' ? 'Drafts from Studio and from cron campaigns land here for review.' : 'Posts appear in this list as they move through the workflow.'}
        </Empty>
      )}
      {data?.map((p) => <PostCard key={`${p.id}-${p.status}`} post={p} onChange={reload} />)}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { PaperPlaneTilt } from '@phosphor-icons/react'
import { createPost } from '../api'
import PostCard from '../PostCard'
import { Button, ErrorNote, Field, ICON, PageHead, Skeleton, inputCls } from '../ui'

const EXAMPLE = 'Announce that Postpilot is open source: an agent that drafts social posts and waits for a human to approve each one.'

export default function Studio() {
  const [brief, setBrief] = useState(EXAMPLE)
  const [platform, setPlatform] = useState('x')
  const [tone, setTone] = useState('friendly')
  const [urls, setUrls] = useState('')
  const [useLlm, setUseLlm] = useState(false)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [post, setPost] = useState(null)
  const [error, setError] = useState('')
  const timer = useRef(null)

  useEffect(() => () => clearInterval(timer.current), [])

  async function run(e) {
    e.preventDefault()
    setRunning(true); setError(''); setPost(null); setElapsed(0)
    timer.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    try {
      const list = urls.split(',').map((u) => u.trim()).filter(Boolean)
      setPost(await createPost({ brief, platform, tone, urls: list, use_llm: useLlm }))
    } catch (err) {
      setError(err.message)
    } finally {
      clearInterval(timer.current)
      setRunning(false)
    }
  }

  return (
    <div>
      <PageHead title="Studio">
        Write a brief. The agent researches, drafts and checks the rules, then stops and waits for you.
      </PageHead>
      <div className="grid gap-12 lg:grid-cols-[22rem_1fr]">
        <form onSubmit={run} className="flex flex-col gap-5">
          <Field label="Brief" hint="What the post should say, in your words.">
            <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={5} required minLength={3} maxLength={1000} className={inputCls} />
          </Field>
          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="mb-2 font-medium">Platform</legend>
            <div className="grid grid-cols-2 gap-2">
              {[['x', 'X, 280 characters'], ['linkedin', 'LinkedIn, 3000']].map(([id, label]) => (
                <label key={id} className={`cursor-pointer rounded-md border px-3 py-2 text-center ${platform === id ? 'border-ink bg-ink text-white' : 'border-line hover:border-ink'}`}>
                  <input type="radio" name="platform" value={id} checked={platform === id} onChange={() => setPlatform(id)} className="sr-only" />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <Field label="Tone">
            <select value={tone} onChange={(e) => setTone(e.target.value)} className={inputCls}>
              {['friendly', 'professional', 'playful', 'direct'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Reference links" hint="Optional, comma separated. The agent reads these pages.">
            <input value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="https://example.com/launch-notes" className={inputCls} />
          </Field>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} className="mt-1 h-4 w-4 accent-[#c8341c]" />
            <span>
              <span className="font-medium">Use the local model</span>
              <span className="block text-xs text-muted">Ollama qwen2.5:3b. Takes 30 to 120 seconds on a CPU. Off uses the instant template drafter.</span>
            </span>
          </label>
          <Button variant="stamp" type="submit" disabled={running}><PaperPlaneTilt {...ICON} />{running ? `Running, ${elapsed}s` : 'Run the agent'}</Button>
          <ErrorNote>{error}</ErrorNote>
        </form>

        <section aria-live="polite">
          {running && (
            <div className="flex flex-col gap-3 border-t border-ink pt-6">
              <p className="text-sm text-muted">Researching, drafting, checking rules. {useLlm ? 'The local model is slow on a CPU.' : ''}</p>
              <Skeleton className="h-5 w-3/4" /><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-2/3" />
            </div>
          )}
          {!running && !post && !error && (
            <div className="border-t border-ink pt-6">
              <p className="text-lg font-medium tracking-tight">Nothing drafted yet</p>
              <p className="mt-2 max-w-[52ch] text-muted">Run the agent with the example brief to see the pause at the human gate. Nothing is published until you approve it.</p>
            </div>
          )}
          {post && (
            <>
              <PostCard key={post.id} post={post} onChange={setPost} />
              <p className="mt-6 text-sm text-muted">Every pending post also lives in <Link to="/queue" className="text-ink underline">Approvals</Link>, so you can leave and come back.</p>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

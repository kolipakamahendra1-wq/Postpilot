import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LinkSimple } from '@phosphor-icons/react'
import { connections, getToken, health, oauthStart, setToken } from '../api'
import { Button, ErrorNote, Field, ICON, PageHead, Skeleton, StatusChip, inputCls, useAsync } from '../ui'

const NAMES = { x: 'X', linkedin: 'LinkedIn' }

export default function Connections() {
  const [params] = useSearchParams()
  const conns = useAsync(connections)
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [token, setTokenValue] = useState(getToken())
  const [saved, setSaved] = useState(false)

  useEffect(() => { health().then(setInfo).catch(() => setInfo(false)) }, [])

  async function connect(provider) {
    setError('')
    try { window.location.href = (await oauthStart(provider)).url } catch (e) { setError(e.message) }
  }

  return (
    <div>
      <PageHead title="Connections">
        Link the accounts Postpilot publishes to. With the mock publisher on, nothing leaves this machine.
      </PageHead>
      {params.get('connected') && <p className="mb-6 border-l-2 border-ink bg-panel px-3 py-2 text-sm">{NAMES[params.get('connected')]} is connected.</p>}
      {params.get('error') && <div className="mb-6"><ErrorNote>OAuth failed: {params.get('error')}</ErrorNote></div>}
      <ErrorNote>{error || conns.error}</ErrorNote>

      <section className="mt-6">
        <h2 className="mb-2 text-lg font-medium tracking-tight">Social accounts</h2>
        {conns.loading && <Skeleton className="h-14 w-full" />}
        <ul className="divide-y divide-line border-y border-line">
          {conns.data?.map((c) => (
            <li key={c.provider} className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div>
                <p className="font-medium">{NAMES[c.provider]}</p>
                <p className="text-sm text-muted">
                  {c.connected ? 'Tokens stored, encrypted.' : c.configured ? 'Ready to connect with OAuth 2 and PKCE.' : `Set ${c.provider.toUpperCase()}_CLIENT_ID and ${c.provider.toUpperCase()}_CLIENT_SECRET on the server first.`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {c.connected && <StatusChip status="published" />}
                <Button variant="ghost" onClick={() => connect(c.provider)}><LinkSimple {...ICON} />{c.connected ? 'Reconnect' : 'Connect'}</Button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-12 grid gap-12 md:grid-cols-2">
        <div>
          <h2 className="mb-2 text-lg font-medium tracking-tight">Slack approvals</h2>
          <p className="text-sm text-muted">Drafts post to a channel with Approve and Reject buttons. Button clicks are checked against the Slack signing secret.</p>
          <dl className="mt-4 divide-y divide-line border-y border-line text-sm">
            <div className="flex justify-between py-2"><dt>Incoming webhook</dt><dd className="font-mono">{info?.slack ? 'set' : 'not set'}</dd></div>
            <div className="flex justify-between py-2"><dt>Signing secret</dt><dd className="font-mono">{info?.slack_signing ? 'set' : 'not set'}</dd></div>
          </dl>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); setToken(token === 'pp-demo-token' ? '' : token); setSaved(true); conns.reload() }} className="flex flex-col gap-3">
          <h2 className="text-lg font-medium tracking-tight">API token</h2>
          <Field label="Bearer token" hint="Stored in this browser only. Must match POSTPILOT_TOKEN on the server.">
            <input value={token} onChange={(e) => { setTokenValue(e.target.value); setSaved(false) }} className={`${inputCls} font-mono`} />
          </Field>
          <Button type="submit" variant="ghost" className="self-start">{saved ? 'Saved' : 'Save token'}</Button>
        </form>
      </section>
    </div>
  )
}

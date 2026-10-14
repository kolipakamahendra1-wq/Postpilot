import { PageHead } from '../ui'

const API = [
  ['POST', '/api/posts', 'Run the agent on a brief. Returns the draft, paused for approval.'],
  ['GET', '/api/posts?status=', 'List posts, optionally by status.'],
  ['POST', '/api/posts/{id}/decision', 'approve, edit or reject. Resumes the paused run.'],
  ['POST', '/api/scheduler/tick', 'Publish everything that is due, now.'],
  ['GET/POST', '/api/campaigns', 'List or add cron campaigns. Each firing creates a draft.'],
  ['POST', '/api/campaigns/{id}/run', 'Fire a campaign immediately.'],
  ['GET', '/api/oauth/{provider}/start', 'Begin OAuth 2 with PKCE. Returns the authorize URL.'],
  ['POST', '/slack/actions', 'Slack button callback. Signature verified, no bearer token.'],
  ['GET', '/api/audit', 'Who did what, newest first.'],
]

function Section({ title, children }) {
  return (
    <section className="border-t border-line py-8 md:grid md:grid-cols-[14rem_1fr] md:gap-10">
      <h2 className="mb-3 font-medium tracking-tight md:mb-0">{title}</h2>
      <div className="max-w-[65ch] leading-relaxed text-muted [&_code]:font-mono [&_code]:text-sm [&_code]:text-ink [&_p+p]:mt-3">{children}</div>
    </section>
  )
}

export default function Docs() {
  return (
    <div>
      <PageHead title="Docs">How the agent works, what is enforced, and where it stops.</PageHead>

      <Section title="The workflow">
        <p>A LangGraph graph runs <code>research, draft, check, approval, schedule</code>. The check step loops back to draft up to three times when a rule fails, passing the violations to the model as feedback.</p>
        <p>The approval step calls <code>interrupt()</code>. The run is saved to SQLite and stops. A server restart does not lose it. Approving from the web or from Slack resumes the same run.</p>
      </Section>
      <Section title="Rules, not just a model">
        <p>A 3B model misses obvious problems, so deterministic checks run beside it: platform length (X counts every link as 23 characters), hashtag cap, banned phrases, and near-duplicates of recent posts. A draft that breaks length cannot be approved.</p>
      </Section>
      <Section title="Tools">
        <p>The agent can call <code>fetch_url</code>, <code>trending_topics</code>, <code>hashtag_suggest</code> and <code>char_limit</code>. The model only picks tools; it may fetch only links you supplied, and fetches block private addresses. A failing tool is recorded and skipped.</p>
      </Section>
      <Section title="Publishing">
        <p>Each post is claimed with one atomic database update before it is sent, so two workers or a double click cannot publish it twice. Failures retry up to three times with growing delays. The default publisher is a mock; set <code>PUBLISHER=live</code> after connecting accounts.</p>
      </Section>
      <Section title="API">
        <p>Every <code>/api</code> route needs <code>Authorization: Bearer &lt;token&gt;</code>.</p>
        <table className="mt-4 w-full text-left text-sm">
          <tbody className="divide-y divide-line border-y border-line">
            {API.map(([m, p, d]) => (
              <tr key={p} className="align-top">
                <td className="whitespace-nowrap py-2 pr-4 font-mono text-xs">{m}</td>
                <td className="py-2 pr-4 font-mono text-xs text-ink">{p}</td>
                <td className="py-2">{d}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Limits">
        <p>Single user, SQLite, one process. The X and LinkedIn adapters and the Slack integration are written against the public docs but not yet run against the real services. A crash during a send leaves the post in <code>publishing</code> rather than risk a double post.</p>
      </Section>
    </div>
  )
}

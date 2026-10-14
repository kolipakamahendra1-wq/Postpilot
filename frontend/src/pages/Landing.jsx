import { Link } from 'react-router-dom'
import { ArrowRight } from '@phosphor-icons/react'
import { ICON } from '../ui'

const STEPS = [
  ['research', 'Read 2 links, pulled 3 headlines', true],
  ['draft', 'Attempt 2 of 3, fixed 291 characters down to 262', true],
  ['check', 'Length, hashtags, banned phrases, duplicates: passed', true],
  ['approval', 'Paused. Waiting for a human.', false],
]

function HeroRun() {
  return (
    <div className="relative border border-ink bg-panel p-5 sm:p-6" aria-label="Example agent run">
      <p className="flex items-center justify-between font-mono text-xs text-muted">
        <span>run #47 on X</span><span>14 Oct, 09:12</span>
      </p>
      <ol className="mt-4 divide-y divide-line border-y border-line text-sm">
        {STEPS.map(([name, detail, done]) => (
          <li key={name} className="grid grid-cols-[5.5rem_1fr] gap-3 py-2.5">
            <span className={`font-mono text-xs ${done ? 'text-muted' : 'font-medium text-stamp'}`}>{name}</span>
            <span className={done ? '' : 'font-medium'}>{detail}</span>
          </li>
        ))}
      </ol>
      <blockquote className="mt-5 text-base leading-relaxed">
        Postpilot is open source. It drafts the post, checks the rules, and then waits for you to say yes.
        <span className="mt-2 block text-sm text-muted">#OpenSource #Agents</span>
      </blockquote>
      <span className="stamp absolute -bottom-3 right-4 border-2 border-stamp bg-paper px-3 py-1 font-mono text-sm font-semibold text-stamp sm:right-6">
        NEEDS APPROVAL
      </span>
    </div>
  )
}

const PROBLEMS = [
  ['The model writes 300 characters for a 280 limit', 'Rules run after every draft. Failures go back to the model as feedback, three tries, then a safe trim. A draft that is still too long cannot be approved.'],
  ['The agent decides to publish on its own', 'The graph stops at an interrupt. Only a decision from the web app or a signed Slack click resumes it.'],
  ['A double click, or Slack plus web, posts twice', 'Each decision and each publish is an atomic database claim. The second caller gets a conflict.'],
  ['The 3B model invents a URL to fetch', 'Tool calls are validated. Only links you gave the agent are fetched, and private addresses are refused.'],
  ['The model is down or returns junk', 'Each step degrades alone: a template drafter, a default tool plan. The run still reaches the approval gate.'],
]

export default function Landing() {
  return (
    <div className="flex flex-col gap-24 pb-8">
      <section className="grid items-center gap-12 pt-4 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <h1 className="max-w-[18ch] text-4xl font-semibold leading-[1.05] tracking-tighter md:text-5xl">An agent that writes the post and waits for your yes.</h1>
          <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-muted">
            Postpilot researches a topic, drafts for X or LinkedIn, checks the result against your rules, and stops. Nothing is published until a person approves it, in the web app or in Slack.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/studio" className="btn inline-flex items-center gap-2 rounded-md border border-stamp bg-stamp px-5 py-2.5 text-sm font-medium text-white hover:bg-[#b02c16]">Open Studio <ArrowRight {...ICON} /></Link>
            <Link to="/docs" className="btn inline-flex items-center rounded-md border border-line px-5 py-2.5 text-sm font-medium hover:border-ink">How it works</Link>
          </div>
        </div>
        <HeroRun />
      </section>

      <section className="grid gap-10 border-t border-ink pt-8 md:grid-cols-[14rem_1fr]">
        <h2 className="text-xl font-semibold tracking-tight">What goes wrong, and what stops it</h2>
        <dl className="divide-y divide-line border-y border-line">
          {PROBLEMS.map(([problem, fix]) => (
            <div key={problem} className="grid gap-1 py-5 md:grid-cols-[1fr_1.4fr] md:gap-8">
              <dt className="font-medium">{problem}</dt>
              <dd className="max-w-[60ch] text-muted">{fix}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="grid gap-10 md:grid-cols-[14rem_1fr]">
        <h2 className="text-xl font-semibold tracking-tight">Runs on your machine</h2>
        <div className="max-w-[62ch] text-muted">
          <p>A local Ollama model writes the drafts, so there is no API bill. The default publisher is a mock, so a demo never touches a real account. Switch on X or LinkedIn after connecting them with OAuth 2 and PKCE.</p>
          <p className="mt-4">Cron campaigns draft on a timetable, for example every Monday at 09:00. They add to the approval queue and never publish by themselves.</p>
          <Link to="/schedule" className="mt-6 inline-flex items-center gap-2 font-medium text-ink underline decoration-stamp decoration-2 underline-offset-4">Set up a campaign <ArrowRight {...ICON} /></Link>
        </div>
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { GithubLogo } from '@phosphor-icons/react'
import { health } from './api'
import Landing from './pages/Landing'
import Studio from './pages/Studio'
import Queue from './pages/Queue'
import Schedule from './pages/Schedule'
import Connections from './pages/Connections'
import Docs from './pages/Docs'

const NAV = [
  ['/studio', 'Studio'],
  ['/queue', 'Approvals'],
  ['/schedule', 'Schedule'],
  ['/connections', 'Connections'],
  ['/docs', 'Docs'],
]

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid h-6 w-6 grid-cols-2 gap-[3px] rounded-[5px] bg-ink p-[5px]" aria-hidden="true">
        <span className="bg-white" />
        <span className="bg-stamp" />
      </span>
      Postpilot
    </Link>
  )
}

function ApiPill() {
  const [info, setInfo] = useState(null)
  useEffect(() => { health().then(setInfo).catch(() => setInfo(false)) }, [])
  if (info === null) return null
  return (
    <span className="hidden items-center gap-2 text-xs text-muted sm:flex" title={info ? `${info.llm} / ${info.model}, publisher ${info.publisher}` : 'API is down'}>
      <span className={`h-2 w-2 rounded-full ${info ? 'bg-ink' : 'bg-stamp'}`} />
      {info ? `API up, ${info.publisher} publisher` : 'API offline'}
    </span>
  )
}

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <div className="flex min-h-[100dvh] flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Logo />
          <nav className="order-3 flex w-full gap-5 overflow-x-auto text-sm sm:order-none sm:w-auto" aria-label="Main">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `whitespace-nowrap py-1 ${isActive ? 'font-medium text-ink underline decoration-stamp decoration-2 underline-offset-8' : 'text-muted hover:text-ink'}`}>
                {label}
              </NavLink>
            ))}
          </nav>
          <ApiPill />
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/studio" element={<Studio />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/schedule" element={<Schedule />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="*" element={<p className="py-20 text-muted">No page here. <Link className="text-ink underline" to="/">Go home</Link>.</p>} />
        </Routes>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-sm text-muted sm:px-6">
          <span>Postpilot. Local model, mock publisher by default.</span>
          <nav className="flex gap-5" aria-label="Footer">
            <Link to="/docs" className="hover:text-ink">Docs</Link>
            <Link to="/connections" className="hover:text-ink">Connections</Link>
            <a href="https://github.com/kolipakamahendra1-wq" className="flex items-center gap-1 hover:text-ink"><GithubLogo size={16} /> GitHub</a>
          </nav>
        </div>
      </footer>
    </div>
  )
}

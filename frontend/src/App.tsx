import { useState } from 'react'
import FounderScreen from './screens/FounderScreen'
import PipelineScreen from './screens/PipelineScreen'
import QueueScreen from './screens/QueueScreen'
import { getActor, setActor, useRoute } from './useRoute'

/** Root shell: hash routing, the "Acting as" actor field, and the three screens. */
export default function App() {
  const route = useRoute()
  const [actor, setActorState] = useState(getActor())

  const onActor = (value: string) => {
    setActorState(value)
    setActor(value)
  }

  const tab = (href: string, label: string, active: boolean) => (
    <a href={href}
       aria-current={active ? 'page' : undefined}
       className={`rounded-md px-3 py-1.5 text-sm font-medium ${
         active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'}`}>
      {label}
    </a>
  )

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-4 py-3">
          <a href="#/" className="mr-2 text-sm font-semibold tracking-tight">
            Founder Engagement Workflow
          </a>
          <nav className="flex gap-1" aria-label="Main">
            {tab('#/', 'Priority Queue', route.name === 'queue')}
            {tab('#/pipeline', 'Pipeline & Dashboard', route.name === 'pipeline')}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="actor" className="text-xs text-slate-500">
              Acting as
            </label>
            <input id="actor" value={actor} onChange={(e) => onActor(e.target.value)}
                   className="w-28 rounded border border-slate-300 px-2 py-1 text-sm"
                   aria-describedby="actor-help" />
            <span id="actor-help" className="sr-only">
              Every human decision is recorded against this name in the audit log.
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-5">
        {route.name === 'queue' && <QueueScreen actor={actor} />}
        {route.name === 'founder' && <FounderScreen id={route.id} actor={actor} />}
        {route.name === 'pipeline' && <PipelineScreen actor={actor} />}
      </main>

      <footer className="mx-auto max-w-[1400px] px-4 pb-8 text-xs text-slate-400">
        Decision support for people. The machine sets attention, potential, evidence
        confidence, data state and a recommended action; a person sets disposition and stage.
      </footer>
    </div>
  )
}

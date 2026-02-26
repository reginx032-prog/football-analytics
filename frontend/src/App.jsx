import { useState } from 'react'
import LeagueTables from './components/LeagueTables.jsx'
import UpcomingOdds from './components/UpcomingOdds.jsx'
import ValueBets from './components/ValueBets.jsx'
import HistoricalBets from './components/HistoricalBets.jsx'

const TABS = [
  { label: 'Tabele',      icon: '▤' },
  { label: 'Mecze',       icon: '◷' },
  { label: 'Value Bets',  icon: '◈' },
  { label: 'Historical',  icon: '◉' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState(0)

  return (
    <div className="app">
      <header className="header">
        <div className="header-top">
          <h1>Football Analytics</h1>
          <span className="header-sub">Model v2.0</span>
        </div>
        <nav className="tabs">
          {TABS.map((tab, i) => (
            <button
              key={tab.label}
              className={`tab-btn ${activeTab === i ? 'active' : ''}`}
              onClick={() => setActiveTab(i)}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="content">
        {activeTab === 0 && <LeagueTables />}
        {activeTab === 1 && <UpcomingOdds />}
        {activeTab === 2 && <ValueBets />}
        {activeTab === 3 && <HistoricalBets />}
      </main>
    </div>
  )
}

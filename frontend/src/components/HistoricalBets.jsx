import { useState, useEffect, useMemo } from 'react'
import { fetchHistoricalBets } from '../api/api.js'

function SortIcon({ dir }) {
  return <span className="sort-icon">{dir === 'asc' ? '↑' : dir === 'desc' ? '↓' : '↕'}</span>
}

const fmtDate = d => d
  ? new Date(d).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '-'

const fmtPln = val => {
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(2)} PLN`
}

export default function HistoricalBets() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [sortKey, setSortKey]             = useState('date')
  const [sortDir, setSortDir]             = useState('desc')
  const [selectedMarkets, setSelectedMarkets] = useState(new Set())
  const [selectedLeagues, setSelectedLeagues] = useState(new Set())

  useEffect(() => {
    fetchHistoricalBets()
      .then(res => setData(res.data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'date' ? 'desc' : 'desc')
    }
  }

  const allMarkets = useMemo(() =>
    data ? [...new Set(data.bets.map(b => b.market))].sort() : []
  , [data])

  const allLeagues = useMemo(() =>
    data ? [...new Set(data.bets.map(b => b.leagueName))].sort() : []
  , [data])

  function toggleMarket(m) {
    setSelectedMarkets(prev => {
      const next = new Set(prev)
      next.has(m) ? next.delete(m) : next.add(m)
      return next
    })
  }

  function toggleLeague(l) {
    setSelectedLeagues(prev => {
      const next = new Set(prev)
      next.has(l) ? next.delete(l) : next.add(l)
      return next
    })
  }

  const filteredBets = useMemo(() => {
    if (!data) return []
    return data.bets.filter(b =>
      (selectedMarkets.size === 0 || selectedMarkets.has(b.market)) &&
      (selectedLeagues.size === 0 || selectedLeagues.has(b.leagueName))
    )
  }, [data, selectedMarkets, selectedLeagues])

  const filteredStats = useMemo(() => {
    if (!filteredBets.length) return null
    const wonCount  = filteredBets.filter(b => b.betResult === 'won').length
    const lostCount = filteredBets.length - wonCount
    const totalPnl  = filteredBets.reduce((s, b) => s + (b.betResult === 'won' ? (b.bookieOdd - 1) * 100 : -100), 0)
    const yieldPct  = totalPnl / (filteredBets.length * 100) * 100
    const avgOdds   = filteredBets.reduce((s, b) => s + b.bookieOdd, 0) / filteredBets.length
    return { totalBets: filteredBets.length, wonCount, lostCount, yieldPct, totalPnlPln: totalPnl, avgOdds }
  }, [filteredBets])

  const sortedBets = useMemo(() => {
    if (!data) return []
    return [...filteredBets].sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb, 'pl') : Number(va) - Number(vb)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filteredBets, sortKey, sortDir])

  if (loading) return <div className="status-box"><span className="spinner" />Ładowanie historii...</div>
  if (error)   return <div className="status-box error">⚠ Błąd: {error}</div>
  if (!data || !data.bets.length) return <div className="status-box">Brak zakończonych zakładów.</div>

  const stats = filteredStats || data.stats

  return (
    <div>
      <div className="section-header">
        <span className="section-title">Historia zakładów</span>
        <span className="badge">{stats.totalBets} / {data.bets.length} zakładów</span>
      </div>
      <div className="selector-pills" style={{marginBottom: '6px'}}>
        {allMarkets.map(m => (
          <button
            key={m}
            className={`pill ${selectedMarkets.has(m) ? 'pill-active' : ''}`}
            onClick={() => toggleMarket(m)}
          >
            {m}
          </button>
        ))}
      </div>
      <div className="selector-pills" style={{marginBottom: '12px'}}>
        {allLeagues.map(l => (
          <button
            key={l}
            className={`pill ${selectedLeagues.has(l) ? 'pill-active' : ''}`}
            onClick={() => toggleLeague(l)}
          >
            {l}
          </button>
        ))}
      </div>

      {/* Karta statystyk */}
      <div className="hist-stats-grid">
        <div className="hist-stat-card">
          <span className="hist-stat-label">Wygranych</span>
          <span className="hist-stat-value won">{stats.wonCount}</span>
        </div>
        <div className="hist-stat-card">
          <span className="hist-stat-label">Przegranych</span>
          <span className="hist-stat-value lost">{stats.lostCount}</span>
        </div>
        <div className="hist-stat-card">
          <span className="hist-stat-label">Yield</span>
          <span className={`hist-stat-value ${stats.yieldPct >= 0 ? 'won' : 'lost'}`}>
            {stats.yieldPct >= 0 ? '+' : ''}{stats.yieldPct.toFixed(2)}%
          </span>
        </div>
        <div className="hist-stat-card">
          <span className="hist-stat-label">P&L (100 PLN/zakład)</span>
          <span className={`hist-stat-value ${stats.totalPnlPln >= 0 ? 'won' : 'lost'}`}>
            {fmtPln(stats.totalPnlPln)}
          </span>
        </div>
        <div className="hist-stat-card">
          <span className="hist-stat-label">Średni kurs</span>
          <span className="hist-stat-value">{stats.avgOdds.toFixed(3)}</span>
        </div>
      </div>

      {/* Tabela */}
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th className={`th-sortable ${sortKey === 'date' ? 'th-active' : ''}`} onClick={() => handleSort('date')}>
                Data <SortIcon dir={sortKey === 'date' ? sortDir : null} />
              </th>
              <th>Liga</th>
              <th>Mecz</th>
              <th>Rynek</th>
              <th>Fair</th>
              <th className={`th-sortable ${sortKey === 'bookieOdd' ? 'th-active' : ''}`} onClick={() => handleSort('bookieOdd')}>
                Kurs <SortIcon dir={sortKey === 'bookieOdd' ? sortDir : null} />
              </th>
              <th className={`th-sortable ${sortKey === 'edge' ? 'th-active' : ''}`} onClick={() => handleSort('edge')}>
                Edge <SortIcon dir={sortKey === 'edge' ? sortDir : null} />
              </th>
              <th>Wynik meczu</th>
              <th>Zakład</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {sortedBets.map(b => {
              const key = `${b.fixtureId}-${b.market}`
              const isWon = b.betResult === 'won'
              const pnl = isWon ? (b.bookieOdd - 1) * 100 : -100
              return (
                <tr key={key} className={`data-row ${isWon ? 'row-won' : 'row-lost'}`}>
                  <td className="date-cell">{fmtDate(b.date)}</td>
                  <td className="league-cell">{b.leagueName}</td>
                  <td className="team-name">
                    {b.homeName} <span className="vs-sep">vs</span> {b.awayName}
                  </td>
                  <td><span className="market-pill">{b.market}</span></td>
                  <td className="odd fair-odd">{b.fairOdd != null ? Number(b.fairOdd).toFixed(3) : '-'}</td>
                  <td className="odd bookie-odd">{b.bookieOdd != null ? Number(b.bookieOdd).toFixed(3) : '-'}</td>
                  <td>
                    <span className="edge-badge">
                      +{b.edge != null ? (b.edge * 100).toFixed(0) : '-'}%
                    </span>
                  </td>
                  <td className="score-cell">
                    {b.goalsHome != null ? `${b.goalsHome} : ${b.goalsAway}` : '-'}
                  </td>
                  <td>
                    <span className={`result-pill ${isWon ? 'result-won' : 'result-lost'}`}>
                      {isWon ? 'TRAFIONY' : 'PUDŁO'}
                    </span>
                  </td>
                  <td className={`pnl-cell ${pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
                    {fmtPln(pnl)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

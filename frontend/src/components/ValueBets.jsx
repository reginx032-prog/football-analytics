import { useState, useEffect, useMemo } from 'react'
import { fetchValueBets } from '../api/api.js'

function SortIcon({ dir }) {
  return <span className="sort-icon">{dir === 'asc' ? '↑' : dir === 'desc' ? '↓' : '↕'}</span>
}

const fmtDate = d => d
  ? new Date(d).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '-'

function edgeClass(edge) {
  if (edge >= 1.00) return 'edge-fire'
  if (edge >= 0.50) return 'edge-strong'
  if (edge >= 0.20) return 'edge-medium'
  return 'edge-mild'
}

function edgeIcon(edge) {
  if (edge >= 1.00) return '🔥'
  if (edge >= 0.50) return '↑↑'
  if (edge >= 0.20) return '↑'
  return '·'
}

export default function ValueBets() {
  const [bets, setBets]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [expanded, setExpanded]           = useState(new Set())
  const [sortKey, setSortKey]             = useState('edge')
  const [sortDir, setSortDir]             = useState('desc')
  const [selectedMarkets, setSelectedMarkets] = useState(new Set())

  useEffect(() => {
    fetchValueBets()
      .then(res => setBets(res.data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'date' ? 'asc' : 'desc')
    }
  }

  const allMarkets = useMemo(() => [...new Set(bets.map(b => b.market))].sort(), [bets])

  function toggleMarket(m) {
    setSelectedMarkets(prev => {
      const next = new Set(prev)
      next.has(m) ? next.delete(m) : next.add(m)
      return next
    })
  }

  const filtered = useMemo(() =>
    selectedMarkets.size === 0 ? bets : bets.filter(b => selectedMarkets.has(b.market))
  , [bets, selectedMarkets])

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb, 'pl') : Number(va) - Number(vb)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortKey, sortDir])

  function toggleRow(key) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  if (loading) return <div className="status-box"><span className="spinner" />Ładowanie value betów...</div>
  if (error)   return <div className="status-box error">⚠ Błąd: {error}</div>
  if (!bets.length) return <div className="status-box">Brak value betów.</div>

  return (
    <div>
      <div className="section-header">
        <span className="section-title">Value Bets</span>
        <span className="badge">{sorted.length} / {bets.length} zakładów</span>
        <a
          href="/api/value-bets/export"
          download="value_bets.xlsx"
          className="export-btn"
        >
          ⬇ Eksportuj do Excel
        </a>
      </div>
      <div className="selector-pills" style={{marginBottom: '12px'}}>
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
                Bukmacher <SortIcon dir={sortKey === 'bookieOdd' ? sortDir : null} />
              </th>
              <th className={`th-sortable ${sortKey === 'edge' ? 'th-active' : ''}`} onClick={() => handleSort('edge')}>
                Edge <SortIcon dir={sortKey === 'edge' ? sortDir : null} />
              </th>
              <th style={{width: '32px'}}></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(b => {
              const key = `${b.fixtureId}-${b.market}`
              const isOpen = expanded.has(key)
              const resultClass = b.betResult === 'won' ? 'row-won' : b.betResult === 'lost' ? 'row-lost' : ''
              return (
                <>
                  <tr
                    key={key}
                    className={`${edgeClass(b.edge)} data-row ${isOpen ? 'row-open' : ''} ${resultClass}`}
                    onClick={() => toggleRow(key)}
                  >
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
                        {edgeIcon(b.edge)} {b.edge != null ? `+${(b.edge * 100).toFixed(0)}%` : '-'}
                      </span>
                    </td>
                    <td className="expand-cell">
                      <span className={`expand-icon ${isOpen ? 'expand-icon--open' : ''}`}>›</span>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr key={`${key}-hints`} className="hints-row">
                      <td colSpan={8}>
                        <div className="hints-panel">
                          <span className="hints-label">Wskazówki modelu</span>
                          <p className="hints-text">{b.hints || 'Brak wskazówek dla tego zakładu.'}</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

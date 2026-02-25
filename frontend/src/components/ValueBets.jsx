import { useState, useEffect } from 'react'
import { fetchValueBets } from '../api/api.js'

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
  const [expanded, setExpanded] = useState(new Set())

  useEffect(() => {
    fetchValueBets()
      .then(res => {
        const sorted = res.data.slice().sort((a, b) => b.edge - a.edge)
        setBets(sorted)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

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
        <span className="badge">{bets.length} zakładów</span>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Liga</th>
              <th>Mecz</th>
              <th>Rynek</th>
              <th>Fair</th>
              <th>Bukmacher</th>
              <th>Edge</th>
              <th style={{width: '32px'}}></th>
            </tr>
          </thead>
          <tbody>
            {bets.map(b => {
              const key = `${b.fixtureId}-${b.market}`
              const isOpen = expanded.has(key)
              return (
                <>
                  <tr
                    key={key}
                    className={`${edgeClass(b.edge)} data-row ${isOpen ? 'row-open' : ''}`}
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

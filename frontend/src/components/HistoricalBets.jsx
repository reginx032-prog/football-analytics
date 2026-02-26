import { useState, useEffect } from 'react'
import { fetchHistoricalBets } from '../api/api.js'

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

  useEffect(() => {
    fetchHistoricalBets()
      .then(res => setData(res.data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="status-box"><span className="spinner" />Ładowanie historii...</div>
  if (error)   return <div className="status-box error">⚠ Błąd: {error}</div>
  if (!data || !data.bets.length) return <div className="status-box">Brak zakończonych zakładów.</div>

  const { bets, stats } = data

  return (
    <div>
      <div className="section-header">
        <span className="section-title">Historia zakładów</span>
        <span className="badge">{stats.totalBets} zakładów</span>
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
              <th>Data</th>
              <th>Liga</th>
              <th>Mecz</th>
              <th>Rynek</th>
              <th>Fair</th>
              <th>Kurs</th>
              <th>Edge</th>
              <th>Wynik meczu</th>
              <th>Zakład</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {bets.map(b => {
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

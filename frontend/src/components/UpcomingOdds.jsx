import { useState, useEffect } from 'react'
import { fetchUpcomingOdds } from '../api/api.js'

const fmt     = v => v != null ? Number(v).toFixed(2) : '-'
const fmtDate = d => d
  ? new Date(d).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '-'

export default function UpcomingOdds() {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    fetchUpcomingOdds()
      .then(res => setMatches(res.data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="status-box"><span className="spinner" />Ładowanie...</div>
  if (error)   return <div className="status-box error">⚠ {error}</div>
  if (!matches.length) return <div className="status-box">Brak nadchodzących meczów.</div>

  return (
    <div>
      <div className="section-header">
        <span className="section-title">Nadchodzące mecze</span>
        <span className="badge">{matches.length}</span>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Liga</th>
              <th>Gospodarz</th>
              <th>Gość</th>
              <th>1</th>
              <th>X</th>
              <th>2</th>
              <th>O 2.5</th>
              <th>U 2.5</th>
              <th className="hide-mobile">BTTS T</th>
              <th className="hide-mobile">BTTS N</th>
            </tr>
          </thead>
          <tbody>
            {matches.map(m => (
              <tr key={m.fixtureId}>
                <td className="date-cell">{fmtDate(m.date)}</td>
                <td className="league-cell">{m.leagueName}</td>
                <td className="team-name">{m.homeName}</td>
                <td className="team-name">{m.awayName}</td>
                <td className="odd">{fmt(m.oddHome)}</td>
                <td className="odd">{fmt(m.oddDraw)}</td>
                <td className="odd">{fmt(m.oddAway)}</td>
                <td className="odd">{fmt(m.oddOver25)}</td>
                <td className="odd">{fmt(m.oddUnder25)}</td>
                <td className="odd hide-mobile">{fmt(m.oddBttsYes)}</td>
                <td className="odd hide-mobile">{fmt(m.oddBttsNo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

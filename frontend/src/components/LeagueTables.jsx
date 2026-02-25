import { useState, useEffect } from 'react'
import { fetchStandings } from '../api/api.js'

export default function LeagueTables() {
  const [grouped, setGrouped]   = useState({})
  const [leagues, setLeagues]   = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  useEffect(() => {
    fetchStandings()
      .then(res => {
        const groups = {}
        res.data.forEach(team => {
          const key = team.leagueName || 'Unknown'
          if (!groups[key]) groups[key] = []
          groups[key].push(team)
        })
        Object.keys(groups).forEach(l => {
          groups[l].sort((a, b) => (a.leagueRank ?? 99) - (b.leagueRank ?? 99))
        })
        const list = Object.keys(groups).sort()
        setGrouped(groups)
        setLeagues(list)
        setSelected(list[0] ?? null)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="status-box"><span className="spinner" />Ładowanie...</div>
  if (error)   return <div className="status-box error">⚠ {error}</div>

  const teams = selected ? (grouped[selected] ?? []) : []

  return (
    <div className="league-tables-view">

      {/* Selektor */}
      <div>
        <span className="selector-label">Wybierz ligę</span>
        <div className="selector-pills">
          {leagues.map(l => (
            <button
              key={l}
              className={`pill ${selected === l ? 'pill-active' : ''}`}
              onClick={() => setSelected(l)}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Tabela */}
      {selected && (
        <div className="table-card">
          <div className="table-card-header">
            <span className="table-card-title">{selected}</span>
            <span className="badge">{teams.length} drużyn</span>
          </div>

          <div className="standings-wrap">
            <table className="standings-table">
              <thead>
                <tr>
                  <th className="col-rank">#</th>
                  <th className="col-team" style={{textAlign:'left'}}>Drużyna</th>
                  <th title="Mecze">M</th>
                  <th title="Wygrane">W</th>
                  <th title="Remisy">R</th>
                  <th title="Porażki">P</th>
                  <th title="Gole">G:S</th>
                  <th title="Różnica">+/-</th>
                  <th title="Punkty">Pkt</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((team, idx) => {
                  const n = teams.length
                  const rowClass = idx < 4 ? 'row-cl' : idx < 6 ? 'row-el' : idx >= n - 3 ? 'row-rel' : ''
                  return (
                    <tr key={team.teamId} className={rowClass}>
                      <td className="col-rank">{team.leagueRank ?? idx + 1}</td>
                      <td className="col-team">{team.teamName}</td>
                      <td>{team.leaguePlayed ?? '-'}</td>
                      <td>{team.leagueWon ?? '-'}</td>
                      <td>{team.leagueDrawn ?? '-'}</td>
                      <td>{team.leagueLost ?? '-'}</td>
                      <td>{team.leagueGf != null ? `${team.leagueGf}:${team.leagueGa}` : '-'}</td>
                      <td className={team.leagueGd > 0 ? 'gd-pos' : team.leagueGd < 0 ? 'gd-neg' : ''}>
                        {team.leagueGd != null ? (team.leagueGd > 0 ? `+${team.leagueGd}` : team.leagueGd) : '-'}
                      </td>
                      <td className="pts">{team.leaguePoints ?? '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="table-legend">
            <span className="legend-item"><span className="legend-bar bar-cl" />Champions League</span>
            <span className="legend-item"><span className="legend-bar bar-el" />Europa League</span>
            <span className="legend-item"><span className="legend-bar bar-rel" />Spadek</span>
          </div>
        </div>
      )}
    </div>
  )
}

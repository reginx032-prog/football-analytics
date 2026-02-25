import { useState, useEffect, useMemo } from 'react'
import { fetchUpcomingOdds } from '../api/api.js'

const fmt     = v => v != null ? Number(v).toFixed(2) : '-'
const fmtDate = d => d
  ? new Date(d).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '-'

const COLS = [
  { key: 'date',       label: 'Data',      sortable: true  },
  { key: 'leagueName', label: 'Liga',      sortable: true  },
  { key: 'homeName',   label: 'Gospodarz', sortable: false },
  { key: 'awayName',   label: 'Gość',      sortable: false },
  { key: 'oddHome',    label: '1',         sortable: true  },
  { key: 'oddDraw',    label: 'X',         sortable: true  },
  { key: 'oddAway',    label: '2',         sortable: true  },
  { key: 'oddOver25',  label: 'O 2.5',     sortable: true  },
  { key: 'oddUnder25', label: 'U 2.5',     sortable: true  },
  { key: 'oddBttsYes', label: 'BTTS T',    sortable: true, mobile: true },
  { key: 'oddBttsNo',  label: 'BTTS N',    sortable: true, mobile: true },
]

function SortIcon({ dir }) {
  return (
    <span className="sort-icon">
      {dir === 'asc' ? '↑' : dir === 'desc' ? '↓' : '↕'}
    </span>
  )
}

export default function UpcomingOdds() {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [sortKey, setSortKey] = useState('date')
  const [sortDir, setSortDir] = useState('asc')

  useEffect(() => {
    fetchUpcomingOdds()
      .then(res => setMatches(res.data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sorted = useMemo(() => {
    return [...matches].sort((a, b) => {
      const va = a[sortKey]
      const vb = b[sortKey]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      const cmp = typeof va === 'string'
        ? va.localeCompare(vb, 'pl')
        : Number(va) - Number(vb)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [matches, sortKey, sortDir])

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
              {COLS.map(col => (
                <th
                  key={col.key}
                  className={[
                    col.mobile   ? 'hide-mobile' : '',
                    col.sortable ? 'th-sortable'  : '',
                    sortKey === col.key ? 'th-active' : '',
                  ].join(' ').trim()}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  {col.label}
                  {col.sortable && <SortIcon dir={sortKey === col.key ? sortDir : null} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(m => (
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

import axios from 'axios'

export const fetchTeamStats    = () => axios.get('/api/teams')
export const fetchStandings    = () => axios.get('/api/standings')
export const fetchUpcomingOdds = () => axios.get('/api/upcoming-odds')
export const fetchValueBets      = () => axios.get('/api/value-bets')
export const fetchHistoricalBets = () => axios.get('/api/historical-bets')

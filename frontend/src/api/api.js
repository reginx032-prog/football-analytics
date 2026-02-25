import axios from 'axios'

export const fetchTeamStats    = () => axios.get('/api/teams')
export const fetchUpcomingOdds = () => axios.get('/api/upcoming-odds')
export const fetchValueBets    = () => axios.get('/api/value-bets')

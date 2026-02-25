package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class TeamStatsL5Dto {

    private Long teamId;
    private String teamName;
    private Double avgGoalsScored;
    private Double avgGoalsConceded;
    private Double avgXgFor;
    private Double avgXgAgainst;
    private Double medGoalsScored;
    private Double medGoalsConceded;
    private Double medXgFor;
    private Double medXgAgainst;
    private Integer totalPointsL5;
    private Double luckFactor;
    private Double defenseLuckFactor;

    // --- Standings (tabela ligowa) ---
    private Long leagueId;
    private String leagueName;
    private Integer leagueRank;
    private Integer leaguePoints;
    private Integer leaguePlayed;
    private Integer leagueWon;
    private Integer leagueDrawn;
    private Integer leagueLost;
    private Integer leagueGf;
    private Integer leagueGa;
    private Integer leagueGd;
}

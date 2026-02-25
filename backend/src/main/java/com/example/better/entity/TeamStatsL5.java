package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

@Entity
@Table(name = "team_stats_last_5")
@Getter
public class TeamStatsL5 {

    @Id
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

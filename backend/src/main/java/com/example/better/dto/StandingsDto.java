package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class StandingsDto {

    private Long teamId;
    private String teamName;
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

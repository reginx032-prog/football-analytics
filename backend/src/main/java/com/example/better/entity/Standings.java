package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

@Entity
@Table(name = "standings")
@Getter
public class Standings {

    @Id
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

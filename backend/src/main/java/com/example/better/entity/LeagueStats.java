package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

@Entity
@Table(name = "league_stats")
@Getter
public class LeagueStats {

    @Id
    private Long leagueId;

    private String leagueName;
    private Double lAvgScoredHome;
    private Double lAvgScoredAway;
    private Double lAvgXgHome;
    private Double lAvgXgAway;
}

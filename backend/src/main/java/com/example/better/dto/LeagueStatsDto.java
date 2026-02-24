package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class LeagueStatsDto {

    private Long leagueId;
    private String leagueName;
    private Double lAvgScoredHome;
    private Double lAvgScoredAway;
    private Double lAvgXgHome;
    private Double lAvgXgAway;
}

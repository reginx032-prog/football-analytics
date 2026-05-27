package com.example.better.dto;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class HistoricalBetDto {

    private Long fixtureId;
    private String market;
    private LocalDateTime date;
    private String leagueName;
    private String homeName;
    private String awayName;
    private Double fairOdd;
    private Double bookieOdd;
    private Double edge;
    private String hints;
    private String betResult;
    private Integer goalsHome;
    private Integer goalsAway;
}

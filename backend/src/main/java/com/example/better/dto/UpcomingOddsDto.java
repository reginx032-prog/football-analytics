package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class UpcomingOddsDto {

    private Long fixtureId;
    private LocalDateTime date;
    private Long homeId;
    private String homeName;
    private Long awayId;
    private String awayName;
    private Long leagueId;
    private String leagueName;
    private Double oddHome;
    private Double oddDraw;
    private Double oddAway;
    private Double oddOver25;
    private Double oddUnder25;
    private Double oddBttsYes;
    private Double oddBttsNo;
    private String sourceBm;
}

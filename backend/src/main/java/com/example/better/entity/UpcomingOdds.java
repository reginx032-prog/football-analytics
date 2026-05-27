package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

import java.time.LocalDateTime;

@Entity
@Table(name = "upcoming_odds")
@Getter
public class UpcomingOdds {

    @Id
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

    @Column(name = "odd_over_25")
    private Double oddOver25;

    @Column(name = "odd_under_25")
    private Double oddUnder25;

    private Double oddBttsYes;
    private Double oddBttsNo;
    private String sourceBm;
    private String isFinished;
}

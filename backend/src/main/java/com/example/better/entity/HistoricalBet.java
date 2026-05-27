package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

import java.time.LocalDateTime;

@Entity
@Table(name = "historical_bets")
@Getter
public class HistoricalBet {

    @EmbeddedId
    private ValueBetId id;

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

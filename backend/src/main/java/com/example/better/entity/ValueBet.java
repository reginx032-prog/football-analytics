package com.example.better.entity;

import jakarta.persistence.*;
import lombok.Getter;

import java.time.LocalDateTime;

@Entity
@Table(name = "value_bets")
@Getter
public class ValueBet {

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
}

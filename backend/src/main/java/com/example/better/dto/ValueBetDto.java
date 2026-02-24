package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ValueBetDto {

    private Long fixtureId;
    private LocalDateTime date;
    private String leagueName;
    private String homeName;
    private String awayName;
    private String market;
    private Double fairOdd;
    private Double bookieOdd;
    private Double edge;
    private String hints;
}

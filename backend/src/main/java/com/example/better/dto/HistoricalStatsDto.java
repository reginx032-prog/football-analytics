package com.example.better.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class HistoricalStatsDto {
    private int totalBets;
    private int wonCount;
    private int lostCount;
    private double yieldPct;
    private double totalPnlPln;
    private double avgOdds;
}

package com.example.better.service;

import com.example.better.dto.HistoricalBetDto;
import com.example.better.dto.HistoricalResponseDto;
import com.example.better.dto.HistoricalStatsDto;
import com.example.better.entity.HistoricalBet;
import com.example.better.repository.HistoricalBetRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class HistoricalService {

    private final HistoricalBetRepository historicalBetRepository;

    public HistoricalResponseDto getHistorical() {
        List<HistoricalBet> all = historicalBetRepository.findAll();
        List<HistoricalBetDto> bets = all.stream().map(this::toDto).toList();

        int totalBets = bets.size();
        long wonCount  = bets.stream().filter(b -> "won".equals(b.getBetResult())).count();
        long lostCount = totalBets - wonCount;

        double totalPnl = bets.stream().mapToDouble(b -> {
            if ("won".equals(b.getBetResult())) return (b.getBookieOdd() - 1) * 100.0;
            return -100.0;
        }).sum();

        double yieldPct = totalBets > 0 ? (totalPnl / (totalBets * 100.0)) * 100.0 : 0;
        double avgOdds  = bets.stream()
                .mapToDouble(b -> b.getBookieOdd() != null ? b.getBookieOdd() : 0)
                .average().orElse(0);

        HistoricalStatsDto stats = new HistoricalStatsDto(
                totalBets,
                (int) wonCount,
                (int) lostCount,
                Math.round(yieldPct * 100.0) / 100.0,
                Math.round(totalPnl * 100.0) / 100.0,
                Math.round(avgOdds * 1000.0) / 1000.0
        );

        return new HistoricalResponseDto(bets, stats);
    }

    private HistoricalBetDto toDto(HistoricalBet entity) {
        HistoricalBetDto dto = new HistoricalBetDto();
        dto.setFixtureId(entity.getId().getFixtureId());
        dto.setMarket(entity.getId().getMarket());
        dto.setDate(entity.getDate());
        dto.setLeagueName(entity.getLeagueName());
        dto.setHomeName(entity.getHomeName());
        dto.setAwayName(entity.getAwayName());
        dto.setFairOdd(entity.getFairOdd());
        dto.setBookieOdd(entity.getBookieOdd());
        dto.setEdge(entity.getEdge());
        dto.setHints(entity.getHints());
        dto.setBetResult(entity.getBetResult());
        dto.setGoalsHome(entity.getGoalsHome());
        dto.setGoalsAway(entity.getGoalsAway());
        return dto;
    }
}

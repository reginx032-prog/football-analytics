package com.example.better.service;

import com.example.better.dto.LeagueStatsDto;
import com.example.better.entity.LeagueStats;
import com.example.better.repository.LeagueStatsRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class LeagueStatsService {

    private final LeagueStatsRepository leagueStatsRepository;

    public List<LeagueStatsDto> getAll() {
        return leagueStatsRepository.findAll().stream()
                .map(this::toDto)
                .toList();
    }

    private LeagueStatsDto toDto(LeagueStats entity) {
        LeagueStatsDto dto = new LeagueStatsDto();
        dto.setLeagueId(entity.getLeagueId());
        dto.setLeagueName(entity.getLeagueName());
        dto.setLAvgScoredHome(entity.getLAvgScoredHome());
        dto.setLAvgScoredAway(entity.getLAvgScoredAway());
        dto.setLAvgXgHome(entity.getLAvgXgHome());
        dto.setLAvgXgAway(entity.getLAvgXgAway());
        return dto;
    }
}

package com.example.better.service;

import com.example.better.dto.StandingsDto;
import com.example.better.entity.Standings;
import com.example.better.repository.StandingsRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class StandingsService {

    private final StandingsRepository standingsRepository;

    public List<StandingsDto> getAll() {
        return standingsRepository.findAll().stream()
                .map(this::toDto)
                .toList();
    }

    private StandingsDto toDto(Standings entity) {
        StandingsDto dto = new StandingsDto();
        dto.setTeamId(entity.getTeamId());
        dto.setTeamName(entity.getTeamName());
        dto.setLeagueId(entity.getLeagueId());
        dto.setLeagueName(entity.getLeagueName());
        dto.setLeagueRank(entity.getLeagueRank());
        dto.setLeaguePoints(entity.getLeaguePoints());
        dto.setLeaguePlayed(entity.getLeaguePlayed());
        dto.setLeagueWon(entity.getLeagueWon());
        dto.setLeagueDrawn(entity.getLeagueDrawn());
        dto.setLeagueLost(entity.getLeagueLost());
        dto.setLeagueGf(entity.getLeagueGf());
        dto.setLeagueGa(entity.getLeagueGa());
        dto.setLeagueGd(entity.getLeagueGd());
        return dto;
    }
}

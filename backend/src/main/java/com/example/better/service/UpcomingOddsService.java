package com.example.better.service;

import com.example.better.dto.UpcomingOddsDto;
import com.example.better.entity.UpcomingOdds;
import com.example.better.repository.UpcomingOddsRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class UpcomingOddsService {

    private final UpcomingOddsRepository upcomingOddsRepository;

    public List<UpcomingOddsDto> getAll() {
        return upcomingOddsRepository.findByIsFinished("no").stream()
                .map(this::toDto)
                .toList();
    }

    private UpcomingOddsDto toDto(UpcomingOdds entity) {
        UpcomingOddsDto dto = new UpcomingOddsDto();
        dto.setFixtureId(entity.getFixtureId());
        dto.setDate(entity.getDate());
        dto.setHomeId(entity.getHomeId());
        dto.setHomeName(entity.getHomeName());
        dto.setAwayId(entity.getAwayId());
        dto.setAwayName(entity.getAwayName());
        dto.setLeagueId(entity.getLeagueId());
        dto.setLeagueName(entity.getLeagueName());
        dto.setOddHome(entity.getOddHome());
        dto.setOddDraw(entity.getOddDraw());
        dto.setOddAway(entity.getOddAway());
        dto.setOddOver25(entity.getOddOver25());
        dto.setOddUnder25(entity.getOddUnder25());
        dto.setOddBttsYes(entity.getOddBttsYes());
        dto.setOddBttsNo(entity.getOddBttsNo());
        dto.setSourceBm(entity.getSourceBm());
        return dto;
    }
}

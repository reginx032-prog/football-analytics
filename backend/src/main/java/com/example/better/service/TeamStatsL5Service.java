package com.example.better.service;

import com.example.better.dto.TeamStatsL5Dto;
import com.example.better.entity.TeamStatsL5;
import com.example.better.repository.TeamStatsL5Repository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class TeamStatsL5Service {

    private final TeamStatsL5Repository teamStatsL5Repository;

    public List<TeamStatsL5Dto> getAll() {
        return teamStatsL5Repository.findAll().stream()
                .map(this::toDto)
                .toList();
    }

    private TeamStatsL5Dto toDto(TeamStatsL5 entity) {
        TeamStatsL5Dto dto = new TeamStatsL5Dto();
        dto.setTeamId(entity.getTeamId());
        dto.setTeamName(entity.getTeamName());
        dto.setAvgGoalsScored(entity.getAvgGoalsScored());
        dto.setAvgGoalsConceded(entity.getAvgGoalsConceded());
        dto.setAvgXgFor(entity.getAvgXgFor());
        dto.setAvgXgAgainst(entity.getAvgXgAgainst());
        dto.setMedGoalsScored(entity.getMedGoalsScored());
        dto.setMedGoalsConceded(entity.getMedGoalsConceded());
        dto.setMedXgFor(entity.getMedXgFor());
        dto.setMedXgAgainst(entity.getMedXgAgainst());
        dto.setTotalPointsL5(entity.getTotalPointsL5());
        dto.setLuckFactor(entity.getLuckFactor());
        dto.setDefenseLuckFactor(entity.getDefenseLuckFactor());
        return dto;
    }
}

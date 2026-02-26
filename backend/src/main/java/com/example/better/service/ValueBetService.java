package com.example.better.service;

import com.example.better.dto.ValueBetDto;
import com.example.better.entity.ValueBet;
import com.example.better.repository.ValueBetRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class ValueBetService {

    private final ValueBetRepository valueBetRepository;

    public List<ValueBetDto> getAll() {
        return valueBetRepository.findAll().stream()
                .map(this::toDto)
                .toList();
    }

    private ValueBetDto toDto(ValueBet entity) {
        ValueBetDto dto = new ValueBetDto();
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
        return dto;
    }
}

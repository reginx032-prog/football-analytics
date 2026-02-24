package com.example.better.controller;

import com.example.better.dto.LeagueStatsDto;
import com.example.better.service.LeagueStatsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/leagues")
@RequiredArgsConstructor
public class LeagueStatsController {

    private final LeagueStatsService leagueStatsService;

    @GetMapping
    public ResponseEntity<List<LeagueStatsDto>> getAll() {
        return ResponseEntity.ok(leagueStatsService.getAll());
    }
}

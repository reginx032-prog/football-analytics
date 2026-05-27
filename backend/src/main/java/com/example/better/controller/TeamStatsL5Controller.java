package com.example.better.controller;

import com.example.better.dto.TeamStatsL5Dto;
import com.example.better.service.TeamStatsL5Service;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/teams")
@RequiredArgsConstructor
public class TeamStatsL5Controller {

    private final TeamStatsL5Service teamStatsL5Service;

    @GetMapping
    public ResponseEntity<List<TeamStatsL5Dto>> getAll() {
        return ResponseEntity.ok(teamStatsL5Service.getAll());
    }
}

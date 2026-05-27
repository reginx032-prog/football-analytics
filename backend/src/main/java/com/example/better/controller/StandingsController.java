package com.example.better.controller;

import com.example.better.dto.StandingsDto;
import com.example.better.service.StandingsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/standings")
@RequiredArgsConstructor
public class StandingsController {

    private final StandingsService standingsService;

    @GetMapping
    public ResponseEntity<List<StandingsDto>> getAll() {
        return ResponseEntity.ok(standingsService.getAll());
    }
}

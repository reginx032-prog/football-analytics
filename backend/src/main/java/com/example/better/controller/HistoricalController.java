package com.example.better.controller;

import com.example.better.dto.HistoricalResponseDto;
import com.example.better.service.HistoricalService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/historical-bets")
@RequiredArgsConstructor
public class HistoricalController {

    private final HistoricalService historicalService;

    @GetMapping
    public ResponseEntity<HistoricalResponseDto> getHistorical() {
        return ResponseEntity.ok(historicalService.getHistorical());
    }
}

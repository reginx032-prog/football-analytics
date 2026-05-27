package com.example.better.controller;

import com.example.better.dto.UpcomingOddsDto;
import com.example.better.service.UpcomingOddsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/upcoming-odds")
@RequiredArgsConstructor
public class UpcomingOddsController {

    private final UpcomingOddsService upcomingOddsService;

    @GetMapping
    public ResponseEntity<List<UpcomingOddsDto>> getAll() {
        return ResponseEntity.ok(upcomingOddsService.getAll());
    }
}

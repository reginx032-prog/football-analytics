package com.example.better.controller;

import com.example.better.dto.ValueBetDto;
import com.example.better.service.ValueBetService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/value-bets")
@RequiredArgsConstructor
public class ValueBetController {

    private final ValueBetService valueBetService;

    @GetMapping
    public ResponseEntity<List<ValueBetDto>> getAll() {
        return ResponseEntity.ok(valueBetService.getAll());
    }
}

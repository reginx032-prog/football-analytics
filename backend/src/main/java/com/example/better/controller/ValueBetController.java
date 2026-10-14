package com.example.better.controller;

import com.example.better.dto.ValueBetDto;
import com.example.better.service.ValueBetService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
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

    @GetMapping("/export")
    public ResponseEntity<byte[]> exportToExcel() throws IOException {
        byte[] file = valueBetService.exportToExcel();
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=value_bets.xlsx")
                .contentType(MediaType.parseMediaType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .body(file);
    }
}

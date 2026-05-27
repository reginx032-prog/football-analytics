package com.example.better.service;

import com.example.better.dto.HistoricalBetDto;
import com.example.better.dto.HistoricalResponseDto;
import com.example.better.dto.HistoricalStatsDto;
import com.example.better.entity.HistoricalBet;
import com.example.better.repository.HistoricalBetRepository;
import lombok.RequiredArgsConstructor;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;

@Service
@RequiredArgsConstructor
public class HistoricalService {

    private final HistoricalBetRepository historicalBetRepository;

    public HistoricalResponseDto getHistorical() {
        List<HistoricalBet> all = historicalBetRepository.findAll();
        List<HistoricalBetDto> bets = all.stream().map(this::toDto).toList();

        int totalBets = bets.size();
        long wonCount  = bets.stream().filter(b -> "won".equals(b.getBetResult())).count();
        long lostCount = totalBets - wonCount;

        double totalPnl = bets.stream().mapToDouble(b -> {
            if ("won".equals(b.getBetResult())) return (b.getBookieOdd() - 1) * 100.0;
            return -100.0;
        }).sum();

        double yieldPct = totalBets > 0 ? (totalPnl / (totalBets * 100.0)) * 100.0 : 0;
        double avgOdds  = bets.stream()
                .mapToDouble(b -> b.getBookieOdd() != null ? b.getBookieOdd() : 0)
                .average().orElse(0);

        HistoricalStatsDto stats = new HistoricalStatsDto(
                totalBets,
                (int) wonCount,
                (int) lostCount,
                Math.round(yieldPct * 100.0) / 100.0,
                Math.round(totalPnl * 100.0) / 100.0,
                Math.round(avgOdds * 1000.0) / 1000.0
        );

        return new HistoricalResponseDto(bets, stats);
    }

    public byte[] exportToExcel() throws IOException {
        List<HistoricalBet> all = historicalBetRepository.findAll();

        try (XSSFWorkbook workbook = new XSSFWorkbook()) {
            Sheet sheet = workbook.createSheet("Historia zakładów");

            // Styl nagłówka
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);
            headerStyle.setFillForegroundColor(IndexedColors.GREY_25_PERCENT.getIndex());
            headerStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            // Nagłówki
            String[] headers = {"Data", "Liga", "Dom", "Gość", "Rynek", "Fair Odd", "Kurs", "Edge %", "Wynik", "Zakład", "P&L (100 PLN)"};
            Row headerRow = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++) {
                Cell cell = headerRow.createCell(i);
                cell.setCellValue(headers[i]);
                cell.setCellStyle(headerStyle);
            }

            // Style wyników
            CellStyle wonStyle = workbook.createCellStyle();
            wonStyle.setFillForegroundColor(IndexedColors.LIGHT_GREEN.getIndex());
            wonStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            CellStyle lostStyle = workbook.createCellStyle();
            lostStyle.setFillForegroundColor(IndexedColors.ROSE.getIndex());
            lostStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            // Dane
            int rowNum = 1;
            for (HistoricalBet b : all) {
                Row row = sheet.createRow(rowNum++);
                boolean isWon = "won".equals(b.getBetResult());
                double pnl = isWon ? (b.getBookieOdd() - 1) * 100.0 : -100.0;

                row.createCell(0).setCellValue(b.getDate() != null ? b.getDate().toString() : "");
                row.createCell(1).setCellValue(b.getLeagueName() != null ? b.getLeagueName() : "");
                row.createCell(2).setCellValue(b.getHomeName() != null ? b.getHomeName() : "");
                row.createCell(3).setCellValue(b.getAwayName() != null ? b.getAwayName() : "");
                row.createCell(4).setCellValue(b.getId().getMarket() != null ? b.getId().getMarket() : "");
                row.createCell(5).setCellValue(b.getFairOdd() != null ? b.getFairOdd() : 0);
                row.createCell(6).setCellValue(b.getBookieOdd() != null ? b.getBookieOdd() : 0);
                row.createCell(7).setCellValue(b.getEdge() != null ? Math.round(b.getEdge() * 100.0) : 0);
                row.createCell(8).setCellValue(b.getGoalsHome() != null ? b.getGoalsHome() + " : " + b.getGoalsAway() : "-");

                Cell resultCell = row.createCell(9);
                resultCell.setCellValue(isWon ? "TRAFIONY" : "PUDŁO");
                resultCell.setCellStyle(isWon ? wonStyle : lostStyle);

                Cell pnlCell = row.createCell(10);
                pnlCell.setCellValue(Math.round(pnl * 100.0) / 100.0);
                pnlCell.setCellStyle(isWon ? wonStyle : lostStyle);
            }

            // Autofit kolumn
            for (int i = 0; i < headers.length; i++) {
                sheet.autoSizeColumn(i);
            }

            ByteArrayOutputStream out = new ByteArrayOutputStream();
            workbook.write(out);
            return out.toByteArray();
        }
    }

    private HistoricalBetDto toDto(HistoricalBet entity) {
        HistoricalBetDto dto = new HistoricalBetDto();
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
        dto.setGoalsHome(entity.getGoalsHome());
        dto.setGoalsAway(entity.getGoalsAway());
        return dto;
    }
}

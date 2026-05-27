package com.example.better.service;

import com.example.better.dto.ValueBetDto;
import com.example.better.entity.ValueBet;
import com.example.better.repository.ValueBetRepository;
import lombok.RequiredArgsConstructor;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
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

    public byte[] exportToExcel() throws IOException {
        List<ValueBet> all = valueBetRepository.findAll();

        try (XSSFWorkbook workbook = new XSSFWorkbook()) {
            Sheet sheet = workbook.createSheet("Value Bets");

            // Styl nagłówka
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);
            headerStyle.setFillForegroundColor(IndexedColors.GREY_25_PERCENT.getIndex());
            headerStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            // Nagłówki
            String[] headers = {"Data", "Liga", "Dom", "Gość", "Rynek", "Fair Odd", "Kurs", "Edge %", "Wskazówki"};
            Row headerRow = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++) {
                Cell cell = headerRow.createCell(i);
                cell.setCellValue(headers[i]);
                cell.setCellStyle(headerStyle);
            }

            // Style edge
            CellStyle fireStyle = workbook.createCellStyle();
            fireStyle.setFillForegroundColor(IndexedColors.ORANGE.getIndex());
            fireStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            CellStyle strongStyle = workbook.createCellStyle();
            strongStyle.setFillForegroundColor(IndexedColors.LIGHT_YELLOW.getIndex());
            strongStyle.setFillPattern(FillPatternType.SOLID_FOREGROUND);

            // Dane
            int rowNum = 1;
            for (ValueBet b : all) {
                Row row = sheet.createRow(rowNum++);
                double edge = b.getEdge() != null ? b.getEdge() : 0;

                row.createCell(0).setCellValue(b.getDate() != null ? b.getDate().toString() : "");
                row.createCell(1).setCellValue(b.getLeagueName() != null ? b.getLeagueName() : "");
                row.createCell(2).setCellValue(b.getHomeName() != null ? b.getHomeName() : "");
                row.createCell(3).setCellValue(b.getAwayName() != null ? b.getAwayName() : "");
                row.createCell(4).setCellValue(b.getId().getMarket() != null ? b.getId().getMarket() : "");
                row.createCell(5).setCellValue(b.getFairOdd() != null ? b.getFairOdd() : 0);

                Cell oddsCell = row.createCell(6);
                oddsCell.setCellValue(b.getBookieOdd() != null ? b.getBookieOdd() : 0);
                if (edge >= 1.0) oddsCell.setCellStyle(fireStyle);
                else if (edge >= 0.5) oddsCell.setCellStyle(strongStyle);

                row.createCell(7).setCellValue(Math.round(edge * 100.0));
                row.createCell(8).setCellValue(b.getHints() != null ? b.getHints() : "");
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

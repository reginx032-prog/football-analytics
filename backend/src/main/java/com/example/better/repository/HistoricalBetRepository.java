package com.example.better.repository;

import com.example.better.entity.HistoricalBet;
import com.example.better.entity.ValueBetId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface HistoricalBetRepository extends JpaRepository<HistoricalBet, ValueBetId> {
}

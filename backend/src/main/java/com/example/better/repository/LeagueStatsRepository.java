package com.example.better.repository;

import com.example.better.entity.LeagueStats;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface LeagueStatsRepository extends JpaRepository<LeagueStats, Long> {
}

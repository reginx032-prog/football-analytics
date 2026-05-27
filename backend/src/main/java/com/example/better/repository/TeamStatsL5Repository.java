package com.example.better.repository;

import com.example.better.entity.TeamStatsL5;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface TeamStatsL5Repository extends JpaRepository<TeamStatsL5, Long> {
}

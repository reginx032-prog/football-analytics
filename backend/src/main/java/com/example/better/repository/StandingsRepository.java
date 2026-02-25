package com.example.better.repository;

import com.example.better.entity.Standings;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface StandingsRepository extends JpaRepository<Standings, Long> {
}

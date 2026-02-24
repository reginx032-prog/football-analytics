package com.example.better.repository;

import com.example.better.entity.UpcomingOdds;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface UpcomingOddsRepository extends JpaRepository<UpcomingOdds, Long> {
}

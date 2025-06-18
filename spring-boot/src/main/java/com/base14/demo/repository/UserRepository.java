package com.base14.demo.repository;

import com.base14.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long>{
    User findFirstById(Long id);
}
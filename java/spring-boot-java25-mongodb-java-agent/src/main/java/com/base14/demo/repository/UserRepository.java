package com.base14.demo.repository;

import com.base14.demo.model.User;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface UserRepository extends MongoRepository<User, String> {
    User findFirstById(String id);
}

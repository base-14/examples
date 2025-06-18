package com.base14.demo.service;

import com.base14.demo.model.User;

import java.util.List;

public interface UserService {

     User save(User user);
     List<User> findAll();
     User findFirstById(Long id);
     void delete(User user);
}

package com.base14.demo.service;

import com.base14.demo.model.User;
import com.base14.demo.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@Transactional
public class UserServiceImpl implements UserService {

    @Autowired
   private UserRepository userRepository;
    private static final Logger logger = LoggerFactory.getLogger(UserServiceImpl.class);

    @Override
    public User save(User user) {
      logger.atInfo().log("Saved user successfully");
      return userRepository.save(user);
    }

    @Override
    public List<User> findAll() {
        return userRepository.findAll();
    }

    @Override
    public User findFirstById(Long id) {
        return userRepository.findFirstById(id);
    }

    @Override
    public void delete(User user) {
        userRepository.delete(user);
    }
}

package com.base14.demo.dto;

import com.base14.demo.entity.User;
import java.time.Instant;

public class AuthDto {

    public record RegisterRequest(String email, String password, String name) {}

    public record LoginRequest(String email, String password) {}

    public record AuthResponse(UserResponse user, String token) {}

    public record UserResponse(Long id, String email, String name, String bio, String image, Instant createdAt) {
        public static UserResponse from(User user) {
            return new UserResponse(user.id, user.email, user.name, user.bio, user.image, user.createdAt);
        }
    }

    public record ErrorResponse(String error, String traceId) {}

    public record MessageResponse(String message) {}
}

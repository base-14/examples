package com.base14.demo.service;

import com.base14.demo.dto.AuthDto.AuthResponse;
import com.base14.demo.dto.AuthDto.LoginRequest;
import com.base14.demo.dto.AuthDto.RegisterRequest;
import com.base14.demo.dto.AuthDto.UserResponse;
import com.base14.demo.entity.User;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.instrumentation.annotations.WithSpan;
import io.smallrye.jwt.build.Jwt;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jboss.logging.Logger;
import org.wildfly.security.password.PasswordFactory;
import org.wildfly.security.password.interfaces.BCryptPassword;
import org.wildfly.security.password.spec.EncryptablePasswordSpec;
import org.wildfly.security.password.spec.IteratedSaltedPasswordAlgorithmSpec;
import org.wildfly.security.password.util.ModularCrypt;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Set;

@ApplicationScoped
public class AuthService {

    private static final Logger LOG = Logger.getLogger(AuthService.class);
    private static final int BCRYPT_ITERATIONS = 10;

    @ConfigProperty(name = "smallrye.jwt.new-token.lifespan", defaultValue = "604800")
    long jwtLifespan;

    @ConfigProperty(name = "mp.jwt.verify.issuer")
    String issuer;

    @WithSpan("auth.register")
    @Transactional
    public AuthResponse register(RegisterRequest request) {
        Span span = Span.current();

        if (User.existsByEmail(request.email())) {
            span.setStatus(StatusCode.ERROR, "email already taken");
            span.recordException(new IllegalArgumentException("email already taken"));
            throw new ServiceException("email already taken", 409);
        }

        User user = new User();
        user.email = request.email();
        user.passwordHash = hashPassword(request.password());
        user.name = request.name();
        user.persist();

        String token = generateToken(user);

        span.setStatus(StatusCode.OK, "user registered");
        LOG.infof("User registered: %d", user.id);

        return new AuthResponse(UserResponse.from(user), token);
    }

    @WithSpan("auth.login")
    public AuthResponse login(LoginRequest request) {
        Span span = Span.current();

        User user = User.findByEmail(request.email());
        if (user == null) {
            span.setStatus(StatusCode.ERROR, "invalid credentials");
            throw new ServiceException("invalid credentials", 401);
        }

        if (!verifyPassword(request.password(), user.passwordHash)) {
            span.setStatus(StatusCode.ERROR, "invalid credentials");
            throw new ServiceException("invalid credentials", 401);
        }

        String token = generateToken(user);

        span.setStatus(StatusCode.OK, "user logged in");
        LOG.infof("User logged in: %d", user.id);

        return new AuthResponse(UserResponse.from(user), token);
    }

    @WithSpan("auth.getUser")
    public User getUser(Long userId) {
        Span span = Span.current();

        User user = User.findById(userId);
        if (user == null) {
            span.setStatus(StatusCode.ERROR, "user not found");
            throw new ServiceException("user not found", 404);
        }

        span.setStatus(StatusCode.OK, "user retrieved");
        return user;
    }

    private String generateToken(User user) {
        return Jwt.issuer(issuer)
                .subject(String.valueOf(user.id))
                .upn(user.email)
                .groups(Set.of("user"))
                .claim("userId", user.id)
                .expiresIn(Duration.ofSeconds(jwtLifespan))
                .sign();
    }

    private String hashPassword(String password) {
        try {
            byte[] salt = new byte[16];
            new SecureRandom().nextBytes(salt);

            PasswordFactory factory = PasswordFactory.getInstance(BCryptPassword.ALGORITHM_BCRYPT);
            IteratedSaltedPasswordAlgorithmSpec spec = new IteratedSaltedPasswordAlgorithmSpec(BCRYPT_ITERATIONS, salt);
            EncryptablePasswordSpec encSpec = new EncryptablePasswordSpec(password.toCharArray(), spec);
            BCryptPassword bcrypt = (BCryptPassword) factory.generatePassword(encSpec);

            return ModularCrypt.encodeAsString(bcrypt);
        } catch (Exception e) {
            throw new RuntimeException("Failed to hash password", e);
        }
    }

    private boolean verifyPassword(String password, String hash) {
        try {
            PasswordFactory factory = PasswordFactory.getInstance(BCryptPassword.ALGORITHM_BCRYPT);
            BCryptPassword bcrypt = (BCryptPassword) factory.translate(ModularCrypt.decode(hash));
            return factory.verify(bcrypt, password.toCharArray());
        } catch (Exception e) {
            return false;
        }
    }
}

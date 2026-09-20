package com.example.support.config;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.ai.retry.TransientAiException;
import org.springframework.ai.retry.autoconfigure.SpringAiRetryAutoConfiguration;
import org.springframework.ai.retry.autoconfigure.SpringAiRetryProperties;
import org.springframework.beans.factory.config.YamlPropertiesFactoryBean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.retry.RetryException;
import org.springframework.core.retry.RetryTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RetryConfigTest {

    @Test
    void applicationYamlSetsMaxAttemptsToZero() {
        var yaml = new YamlPropertiesFactoryBean();
        yaml.setResources(new ClassPathResource("application.yml"));
        var properties = yaml.getObject();

        assertEquals("0", properties.getProperty("spring.ai.retry.max-attempts"));
    }

    @Test
    void maxAttemptsZeroMakesOnlyOneAttempt() {
        var retryProperties = new SpringAiRetryProperties();
        retryProperties.setMaxAttempts(0);
        RetryTemplate retryTemplate = new SpringAiRetryAutoConfiguration().retryTemplate(retryProperties);

        var invocations = new AtomicInteger();
        RetryException thrown = assertThrows(RetryException.class, () -> retryTemplate.execute(() -> {
            invocations.incrementAndGet();
            throw new TransientAiException("connection refused");
        }));

        assertEquals(1, invocations.get());
        assertInstanceOf(TransientAiException.class, thrown.getCause());
    }
}

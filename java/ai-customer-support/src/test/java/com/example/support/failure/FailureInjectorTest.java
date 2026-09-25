package com.example.support.failure;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.example.support.pipeline.SupportPipeline;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FailureInjectorTest {

    private final SupportPipeline pipeline = mock(SupportPipeline.class);
    private final FailureInjector injector = new FailureInjector(pipeline);

    @Test
    void modelNotFoundRunsTheCapableCallOnAMissingModel() {
        when(pipeline.process(anyString(), any(UUID.class), eq(FailureInjector.MISSING_MODEL)))
            .thenReturn(Mono.empty());

        injector.inject("model-not-found").block();

        verify(pipeline).process(anyString(), any(UUID.class), eq(FailureInjector.MISSING_MODEL));
    }

    @Test
    void promptScenariosKeepTheConfiguredModel() {
        when(pipeline.process(anyString(), any(UUID.class), isNull())).thenReturn(Mono.empty());

        injector.inject("rag-miss").block();

        verify(pipeline).process(anyString(), any(UUID.class), isNull());
    }

    @Test
    void modelNotFoundIsListed() {
        assertTrue(injector.listScenarios().containsKey("model-not-found"));
    }

    @Test
    void anUnknownScenarioIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> injector.inject("nope").block());
    }
}

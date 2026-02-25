package com.example.support.failure;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.support.pipeline.SupportPipeline;

import reactor.core.publisher.Mono;

@RestController
@Profile("failure-injection")
@RequestMapping("/api/failures")
public class FailureController {

    private final FailureInjector injector;

    public FailureController(FailureInjector injector) {
        this.injector = injector;
    }

    @GetMapping
    public Map<String, String> listScenarios() {
        return injector.listScenarios();
    }

    @PostMapping("/{scenario}")
    public Mono<SupportPipeline.PipelineResult> inject(@PathVariable String scenario) {
        return injector.inject(scenario);
    }
}

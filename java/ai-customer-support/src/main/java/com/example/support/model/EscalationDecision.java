package com.example.support.model;

public record EscalationDecision(
    boolean shouldEscalate,
    String reason,
    EscalationPriority priority,
    String summary
) {

    public enum EscalationPriority { LOW, MEDIUM, HIGH, URGENT }

    public static EscalationDecision noEscalation() {
        return new EscalationDecision(false, "", EscalationPriority.LOW, "");
    }

    public static EscalationDecision escalate(String reason, EscalationPriority priority, String summary) {
        return new EscalationDecision(true, reason, priority, summary);
    }
}

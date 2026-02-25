use serde::Deserialize;
use std::collections::HashMap;
use std::sync::LazyLock;

#[derive(Debug, Deserialize, Clone)]
pub struct PriceEntry {
    #[allow(dead_code)]
    pub provider: String,
    pub input: f64,
    pub output: f64,
}

#[derive(Deserialize)]
struct PricingFile {
    models: HashMap<String, PriceEntry>,
}

pub static PRICING: LazyLock<HashMap<String, PriceEntry>> = LazyLock::new(|| {
    let env_path = std::env::var("PRICING_JSON_PATH").unwrap_or_default();
    let paths = [
        "/_shared/pricing.json",
        &env_path,
        "_shared/pricing.json",
        "../_shared/pricing.json",
        "../../_shared/pricing.json",
        "../../../_shared/pricing.json",
    ];
    for path in &paths {
        if path.is_empty() {
            continue;
        }
        if let Ok(data) = std::fs::read_to_string(path)
            && let Ok(parsed) = serde_json::from_str::<PricingFile>(&data)
            && !parsed.models.is_empty()
        {
            return parsed.models;
        }
    }
    tracing::warn!("pricing.json not found, costs will be $0.00");
    HashMap::new()
});

pub fn calculate_cost(model: &str, input_tokens: u32, output_tokens: u32) -> f64 {
    match PRICING.get(model) {
        Some(entry) => {
            (f64::from(input_tokens) * entry.input / 1_000_000.0)
                + (f64::from(output_tokens) * entry.output / 1_000_000.0)
        }
        None => 0.0,
    }
}

pub static PROVIDER_SERVERS: LazyLock<HashMap<&str, &str>> = LazyLock::new(|| {
    HashMap::from([
        ("openai", "api.openai.com"),
        ("anthropic", "api.anthropic.com"),
        ("google", "generativelanguage.googleapis.com"),
        ("ollama", "localhost"),
    ])
});

pub static PROVIDER_PORTS: LazyLock<HashMap<&str, i64>> = LazyLock::new(|| {
    HashMap::from([
        ("openai", 443_i64),
        ("anthropic", 443),
        ("google", 443),
        ("ollama", 11434),
    ])
});

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_cost_known_model() {
        assert!(
            PRICING.contains_key("gpt-4.1"),
            "pricing.json must contain gpt-4.1"
        );
        let cost = calculate_cost("gpt-4.1", 1_000_000, 1_000_000);
        assert!(cost > 0.0, "cost should be positive for known model");
    }

    #[test]
    fn test_calculate_cost_unknown_model() {
        let cost = calculate_cost("nonexistent-model-xyz", 1000, 1000);
        assert_eq!(cost, 0.0);
    }

    #[test]
    fn test_calculate_cost_zero_tokens() {
        let cost = calculate_cost("gpt-4.1", 0, 0);
        assert_eq!(cost, 0.0);
    }

    #[test]
    fn test_provider_servers() {
        assert_eq!(PROVIDER_SERVERS.get("openai"), Some(&"api.openai.com"));
        assert_eq!(
            PROVIDER_SERVERS.get("anthropic"),
            Some(&"api.anthropic.com")
        );
        assert_eq!(
            PROVIDER_SERVERS.get("google"),
            Some(&"generativelanguage.googleapis.com")
        );
        assert_eq!(PROVIDER_SERVERS.get("ollama"), Some(&"localhost"));
    }

    #[test]
    fn test_provider_ports() {
        assert_eq!(PROVIDER_PORTS.get("openai"), Some(&443));
        assert_eq!(PROVIDER_PORTS.get("anthropic"), Some(&443));
        assert_eq!(PROVIDER_PORTS.get("google"), Some(&443));
        assert_eq!(PROVIDER_PORTS.get("ollama"), Some(&11434));
    }
}

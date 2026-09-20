use std::collections::HashMap;
use std::sync::LazyLock;

use regex::Regex;
use serde::Deserialize;

const PRICING_JSON: &str = include_str!("../../../../_shared/pricing.json");

#[derive(Debug, Deserialize, Clone)]
pub struct PriceEntry {
    pub input: f64,
    pub output: f64,
}

#[derive(Deserialize)]
struct PricingFile {
    models: HashMap<String, PriceEntry>,
}

pub static PRICING: LazyLock<HashMap<String, PriceEntry>> = LazyLock::new(|| {
    serde_json::from_str::<PricingFile>(PRICING_JSON)
        .expect("_shared/pricing.json must parse")
        .models
});

static DATE_SUFFIX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(-\d{4}-\d{2}-\d{2}|-\d{8})$").unwrap());

static DASH_MINOR_VERSION: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"-(\d+)-(\d+)$").unwrap());

fn normalize_model(model: &str) -> String {
    let without_date = DATE_SUFFIX.replace(model, "");
    DASH_MINOR_VERSION
        .replace(&without_date, "-$1.$2")
        .into_owned()
}

pub fn calculate_cost(model: &str, input_tokens: u32, output_tokens: u32) -> f64 {
    let entry = PRICING
        .get(model)
        .or_else(|| PRICING.get(&normalize_model(model)));

    match entry {
        Some(entry) => {
            (f64::from(input_tokens) * entry.input / 1_000_000.0)
                + (f64::from(output_tokens) * entry.output / 1_000_000.0)
        }
        None => 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pricing_is_embedded_at_build_time() {
        assert!(PRICING.contains_key("gpt-4.1"));
        assert!(PRICING.contains_key("claude-haiku-4.5"));
    }

    #[test]
    fn known_model_costs_by_token_rate() {
        let entry = PRICING.get("gpt-4.1").unwrap();
        let cost = calculate_cost("gpt-4.1", 1_000_000, 1_000_000);
        assert!((cost - (entry.input + entry.output)).abs() < 1e-9);
    }

    #[test]
    fn dated_model_id_normalises_to_the_pricing_key() {
        assert_eq!(
            normalize_model("claude-haiku-4-5-20251001"),
            "claude-haiku-4.5"
        );
        assert_eq!(normalize_model("gpt-4.1-2025-04-14"), "gpt-4.1");
        assert_eq!(normalize_model("claude-sonnet-4-6"), "claude-sonnet-4.6");
        assert_eq!(
            normalize_model("claude-sonnet-4-20250514"),
            "claude-sonnet-4"
        );
    }

    #[test]
    fn dated_model_id_costs_the_same_as_its_pricing_key() {
        assert_eq!(
            calculate_cost("claude-haiku-4-5-20251001", 1000, 1000),
            calculate_cost("claude-haiku-4.5", 1000, 1000)
        );
    }

    #[test]
    fn unknown_model_costs_nothing() {
        assert_eq!(calculate_cost("nonexistent-model-xyz", 1000, 1000), 0.0);
    }

    #[test]
    fn zero_tokens_cost_nothing() {
        assert_eq!(calculate_cost("gpt-4.1", 0, 0), 0.0);
    }
}

use chrono::Datelike;
use serde::{Deserialize, Serialize};

use crate::db::data_points::IndicatorData;
use crate::error::AppError;
use crate::llm::{GenerateRequest, LlmClient};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisResult {
    pub trends: Vec<Trend>,
    pub correlations: Vec<String>,
    pub key_findings: Vec<String>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cost_usd: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trend {
    pub indicator: String,
    pub direction: String,
    pub description: String,
}

#[tracing::instrument(
    name = "pipeline_stage analyze",
    skip(llm_client, data),
    fields(
        pipeline.stage = "analyze",
        analysis.trends_found,
        analysis.key_findings,
    )
)]
pub async fn analyze(
    llm_client: &LlmClient,
    model: &str,
    data: &[IndicatorData],
) -> Result<AnalysisResult, AppError> {
    let mut data_summary = String::new();
    for ind in data {
        data_summary.push_str(&format!("\n## {} ({})\n", ind.name, ind.code));
        data_summary.push_str(&format!(
            "Unit: {}, Frequency: {}\n",
            ind.unit, ind.frequency
        ));

        if let (Some(first), Some(last)) = (ind.values.first(), ind.values.last()) {
            data_summary.push_str(&format!(
                "Range: {} to {}\n",
                first.observation_date, last.observation_date
            ));
            data_summary.push_str(&format!(
                "First value: {:.2}, Last value: {:.2}\n",
                first.value, last.value
            ));
            data_summary.push_str(&format!("Data points: {}\n", ind.values.len()));

            let values: Vec<f64> = ind.values.iter().map(|v| v.value).collect();
            let min = values.iter().cloned().fold(f64::INFINITY, f64::min);
            let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
            let avg = values.iter().sum::<f64>() / values.len() as f64;
            data_summary.push_str(&format!("Min: {min:.2}, Max: {max:.2}, Avg: {avg:.2}\n"));

            for v in ind
                .values
                .iter()
                .filter(|v| v.observation_date.month() == 1)
            {
                data_summary.push_str(&format!("  {}: {:.2}\n", v.observation_date, v.value));
            }
        }
    }

    let system = include_str!("../../data/schema-context.txt").to_string();

    let prompt = format!(
        "Analyze the following economic data and identify trends, correlations, and key findings.\n\
        Return your analysis as JSON with this exact structure:\n\
        {{\n  \"trends\": [{{\"indicator\": \"CODE\", \"direction\": \"increasing|decreasing|stable|volatile\", \"description\": \"...\"}}],\n  \
        \"correlations\": [\"description of correlation between indicators\"],\n  \
        \"key_findings\": [\"important insight 1\", \"important insight 2\"]\n}}\n\n\
        DATA:\n{data_summary}"
    );

    let resp = llm_client
        .generate(&GenerateRequest {
            model: model.to_string(),
            system,
            prompt,
            temperature: 0.3,
            max_tokens: 2048,
            stage: "analyze".to_string(),
        })
        .await
        .map_err(|e| AppError::Llm(e.to_string()))?;

    let analysis = parse_analysis_response(
        &resp.content,
        resp.input_tokens,
        resp.output_tokens,
        resp.cost_usd,
    )?;

    let span = tracing::Span::current();
    span.record("analysis.trends_found", analysis.trends.len());
    span.record("analysis.key_findings", analysis.key_findings.len());

    Ok(analysis)
}

fn parse_analysis_response(
    content: &str,
    input_tokens: u32,
    output_tokens: u32,
    cost_usd: f64,
) -> Result<AnalysisResult, AppError> {
    let json_str = extract_json(content);

    #[derive(Deserialize)]
    struct RawAnalysis {
        trends: Option<Vec<Trend>>,
        correlations: Option<Vec<String>>,
        key_findings: Option<Vec<String>>,
    }

    match serde_json::from_str::<RawAnalysis>(&json_str) {
        Ok(raw) => Ok(AnalysisResult {
            trends: raw.trends.unwrap_or_default(),
            correlations: raw.correlations.unwrap_or_default(),
            key_findings: raw.key_findings.unwrap_or_default(),
            input_tokens,
            output_tokens,
            cost_usd,
        }),
        Err(_) => Ok(AnalysisResult {
            trends: vec![],
            correlations: vec![],
            key_findings: vec![content.chars().take(500).collect::<String>()],
            input_tokens,
            output_tokens,
            cost_usd,
        }),
    }
}

pub(crate) fn extract_json(content: &str) -> String {
    if let Some(start) = content.find("```json")
        && let Some(end) = content[start + 7..].find("```")
    {
        return content[start + 7..start + 7 + end].trim().to_string();
    }
    if let Some(start) = content.find("```")
        && let Some(end) = content[start + 3..].find("```")
    {
        let inner = content[start + 3..start + 3 + end].trim();
        if inner.starts_with('{') {
            return inner.to_string();
        }
    }
    if let Some(start) = content.find('{')
        && let Some(end) = content.rfind('}')
    {
        return content[start..=end].to_string();
    }
    content.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_json_raw() {
        let input = r#"{"trends": [], "correlations": [], "key_findings": ["test"]}"#;
        let result = extract_json(input);
        assert!(result.starts_with('{'));
        let parsed: serde_json::Value = serde_json::from_str(&result).unwrap();
        assert_eq!(parsed["key_findings"][0], "test");
    }

    #[test]
    fn test_extract_json_markdown_block() {
        let input = "Here is the analysis:\n```json\n{\"trends\": []}\n```\nDone.";
        let result = extract_json(input);
        assert_eq!(result, "{\"trends\": []}");
    }

    #[test]
    fn test_extract_json_generic_code_block() {
        let input = "```\n{\"key\": \"value\"}\n```";
        let result = extract_json(input);
        assert_eq!(result, "{\"key\": \"value\"}");
    }

    #[test]
    fn test_extract_json_embedded_in_text() {
        let input = "The result is {\"a\": 1} and that's it.";
        let result = extract_json(input);
        assert_eq!(result, "{\"a\": 1}");
    }

    #[test]
    fn test_extract_json_no_json() {
        let input = "No JSON here at all";
        let result = extract_json(input);
        assert_eq!(result, input);
    }

    #[test]
    fn test_parse_analysis_valid() {
        let content = r#"{"trends": [{"indicator": "GDP", "direction": "increasing", "description": "rising"}], "correlations": ["GDP and unemployment"], "key_findings": ["economy grew"]}"#;
        let result = parse_analysis_response(content, 100, 50, 0.01).unwrap();
        assert_eq!(result.trends.len(), 1);
        assert_eq!(result.trends[0].indicator, "GDP");
        assert_eq!(result.correlations.len(), 1);
        assert_eq!(result.key_findings.len(), 1);
        assert_eq!(result.input_tokens, 100);
        assert_eq!(result.output_tokens, 50);
    }

    #[test]
    fn test_parse_analysis_invalid_json_fallback() {
        let content = "This is not JSON at all, just plain text analysis";
        let result = parse_analysis_response(content, 200, 100, 0.02).unwrap();
        assert!(result.trends.is_empty());
        assert!(result.correlations.is_empty());
        assert_eq!(result.key_findings.len(), 1);
        assert_eq!(result.input_tokens, 200);
        assert_eq!(result.output_tokens, 100);
    }

    #[test]
    fn test_parse_analysis_partial_fields() {
        let content = r#"{"trends": [{"indicator": "CPI", "direction": "increasing", "description": "inflation"}]}"#;
        let result = parse_analysis_response(content, 50, 25, 0.005).unwrap();
        assert_eq!(result.trends.len(), 1);
        assert!(result.correlations.is_empty());
        assert!(result.key_findings.is_empty());
    }
}

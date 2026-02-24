use serde::{Deserialize, Serialize};

use crate::db::data_points::IndicatorData;
use crate::error::AppError;
use crate::llm::{GenerateRequest, LlmClient};

use super::analyze::AnalysisResult;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NarrativeResult {
    pub title: String,
    pub executive_summary: String,
    pub sections: Vec<NarrativeSection>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cost_usd: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NarrativeSection {
    pub heading: String,
    pub content: String,
}

#[tracing::instrument(
    name = "pipeline_stage generate",
    skip(llm_client, data, analysis),
    fields(
        pipeline.stage = "generate",
        narrative.title,
        narrative.sections_count,
    )
)]
pub async fn generate(
    llm_client: &LlmClient,
    model: &str,
    data: &[IndicatorData],
    analysis: &AnalysisResult,
) -> Result<NarrativeResult, AppError> {
    let indicator_list: Vec<String> = data
        .iter()
        .map(|d| format!("{} ({})", d.name, d.code))
        .collect();

    let time_range = data
        .first()
        .and_then(|ind| {
            let first_date = ind.values.first().map(|v| v.observation_date)?;
            let last_date = ind.values.last().map(|v| v.observation_date)?;
            Some(format!("{first_date} to {last_date}"))
        })
        .unwrap_or_else(|| "unknown".to_string());

    let analysis_json = serde_json::to_string_pretty(analysis).unwrap_or_default();

    let system = "You are an expert economic analyst writing structured reports. \
        Write clear, data-driven narrative with specific numbers and dates. \
        Be concise but thorough."
        .to_string();

    let prompt = format!(
        "Write a structured economic report based on this analysis.\n\n\
        Indicators: {}\n\
        Time period: {}\n\n\
        Analysis:\n{}\n\n\
        Return your report as JSON with this exact structure:\n\
        {{\n  \"title\": \"Report title\",\n  \
        \"executive_summary\": \"2-3 sentence overview\",\n  \
        \"sections\": [\n    {{\"heading\": \"Section title\", \"content\": \"Section content with data references\"}}\n  ]\n}}\n\n\
        Include 3-5 sections covering the major themes from the analysis.",
        indicator_list.join(", "),
        time_range,
        analysis_json
    );

    let resp = llm_client
        .generate(&GenerateRequest {
            model: model.to_string(),
            system,
            prompt,
            temperature: 0.3,
            max_tokens: 4096,
            stage: "generate".to_string(),
        })
        .await
        .map_err(|e| AppError::Llm(e.to_string()))?;

    let narrative = parse_narrative_response(
        &resp.content,
        resp.input_tokens,
        resp.output_tokens,
        resp.cost_usd,
    )?;

    let span = tracing::Span::current();
    span.record("narrative.title", &narrative.title);
    span.record("narrative.sections_count", narrative.sections.len());

    Ok(narrative)
}

fn parse_narrative_response(
    content: &str,
    input_tokens: u32,
    output_tokens: u32,
    cost_usd: f64,
) -> Result<NarrativeResult, AppError> {
    let json_str = super::analyze::extract_json(content);

    #[derive(Deserialize)]
    struct RawNarrative {
        title: Option<String>,
        executive_summary: Option<String>,
        sections: Option<Vec<NarrativeSection>>,
    }

    match serde_json::from_str::<RawNarrative>(&json_str) {
        Ok(raw) => Ok(NarrativeResult {
            title: raw.title.unwrap_or_else(|| "Economic Report".to_string()),
            executive_summary: raw
                .executive_summary
                .unwrap_or_else(|| "Analysis of economic indicators.".to_string()),
            sections: raw.sections.unwrap_or_default(),
            input_tokens,
            output_tokens,
            cost_usd,
        }),
        Err(_) => Ok(NarrativeResult {
            title: "Economic Report".to_string(),
            executive_summary: content.chars().take(500).collect(),
            sections: vec![NarrativeSection {
                heading: "Analysis".to_string(),
                content: content.to_string(),
            }],
            input_tokens,
            output_tokens,
            cost_usd,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_narrative_valid() {
        let content = r#"{"title": "Economic Overview", "executive_summary": "The economy grew.", "sections": [{"heading": "GDP", "content": "GDP increased."}]}"#;
        let result = parse_narrative_response(content, 500, 300, 0.03).unwrap();
        assert_eq!(result.title, "Economic Overview");
        assert_eq!(result.executive_summary, "The economy grew.");
        assert_eq!(result.sections.len(), 1);
        assert_eq!(result.sections[0].heading, "GDP");
        assert_eq!(result.input_tokens, 500);
        assert_eq!(result.output_tokens, 300);
    }

    #[test]
    fn test_parse_narrative_partial() {
        let content = r#"{"title": "Partial Report"}"#;
        let result = parse_narrative_response(content, 100, 50, 0.01).unwrap();
        assert_eq!(result.title, "Partial Report");
        assert_eq!(result.executive_summary, "Analysis of economic indicators.");
        assert!(result.sections.is_empty());
    }

    #[test]
    fn test_parse_narrative_invalid_fallback() {
        let content = "This is not JSON, just a narrative about the economy.";
        let result = parse_narrative_response(content, 200, 100, 0.02).unwrap();
        assert_eq!(result.title, "Economic Report");
        assert_eq!(result.sections.len(), 1);
        assert_eq!(result.sections[0].heading, "Analysis");
    }

    #[test]
    fn test_parse_narrative_markdown_wrapped() {
        let content = "```json\n{\"title\": \"Wrapped\", \"executive_summary\": \"Test\", \"sections\": []}\n```";
        let result = parse_narrative_response(content, 50, 25, 0.005).unwrap();
        assert_eq!(result.title, "Wrapped");
        assert_eq!(result.executive_summary, "Test");
    }
}

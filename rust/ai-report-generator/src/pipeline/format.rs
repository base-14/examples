use std::time::Duration;

use chrono::NaiveDate;
use serde::Serialize;
use uuid::Uuid;

use crate::error::AppError;

use super::analyze::AnalysisResult;
use super::generate::NarrativeResult;
use super::retrieve::RetrieveResult;

#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub id: Uuid,
    pub title: String,
    pub executive_summary: String,
    pub sections: Vec<super::generate::NarrativeSection>,
    pub indicators_used: Vec<String>,
    pub time_range_start: NaiveDate,
    pub time_range_end: NaiveDate,
    pub total_data_points: usize,
    pub total_tokens: u32,
    pub total_cost_usd: f64,
    pub providers_used: Vec<String>,
    pub generation_duration_ms: u64,
    pub trace_id: String,
}

pub struct FormatParams<'a> {
    pub retrieve_result: &'a RetrieveResult,
    pub analysis: &'a AnalysisResult,
    pub narrative: &'a NarrativeResult,
    pub indicators_requested: &'a [String],
    pub start_date: NaiveDate,
    pub end_date: NaiveDate,
    pub duration: Duration,
    pub trace_id: String,
}

#[tracing::instrument(
    name = "pipeline_stage format",
    skip(params),
    fields(
        pipeline.stage = "format",
        report.title,
        report.sections_count,
    )
)]
pub fn format_report(params: FormatParams<'_>) -> Result<Report, AppError> {
    let total_tokens = params.analysis.input_tokens
        + params.analysis.output_tokens
        + params.narrative.input_tokens
        + params.narrative.output_tokens;

    let mut providers_used = vec![params.analysis.provider.clone()];
    if params.narrative.provider != params.analysis.provider {
        providers_used.push(params.narrative.provider.clone());
    }

    let span = tracing::Span::current();
    span.record("report.title", &params.narrative.title);
    span.record("report.sections_count", params.narrative.sections.len());

    Ok(Report {
        id: Uuid::new_v4(),
        title: params.narrative.title.clone(),
        executive_summary: params.narrative.executive_summary.clone(),
        sections: params.narrative.sections.clone(),
        indicators_used: params.indicators_requested.to_vec(),
        time_range_start: params.start_date,
        time_range_end: params.end_date,
        total_data_points: params.retrieve_result.total_data_points,
        total_tokens,
        total_cost_usd: params.analysis.cost_usd + params.narrative.cost_usd,
        providers_used,
        generation_duration_ms: params.duration.as_millis() as u64,
        trace_id: params.trace_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::analyze::{AnalysisResult, Trend};
    use crate::pipeline::generate::{NarrativeResult, NarrativeSection};
    use crate::pipeline::retrieve::RetrieveResult;

    #[test]
    fn test_format_report_assembles_all_fields() {
        let retrieve_result = RetrieveResult {
            indicators: vec![],
            total_data_points: 250,
        };
        let analysis = AnalysisResult {
            trends: vec![Trend {
                indicator: "GDP".to_string(),
                direction: "increasing".to_string(),
                description: "GDP grew".to_string(),
            }],
            correlations: vec!["GDP and employment".to_string()],
            key_findings: vec!["Economy expanded".to_string()],
            input_tokens: 500,
            output_tokens: 200,
            cost_usd: 0.01,
            provider: "openai".to_string(),
        };
        let narrative = NarrativeResult {
            title: "Economic Overview 2023".to_string(),
            executive_summary: "The economy performed well.".to_string(),
            sections: vec![
                NarrativeSection {
                    heading: "GDP Growth".to_string(),
                    content: "GDP increased by 3%.".to_string(),
                },
                NarrativeSection {
                    heading: "Employment".to_string(),
                    content: "Unemployment fell.".to_string(),
                },
            ],
            input_tokens: 800,
            output_tokens: 400,
            cost_usd: 0.02,
            provider: "openai".to_string(),
        };

        let report = format_report(FormatParams {
            retrieve_result: &retrieve_result,
            analysis: &analysis,
            narrative: &narrative,
            indicators_requested: &["GDP".to_string(), "UNRATE".to_string()],
            start_date: NaiveDate::from_ymd_opt(2003, 1, 1).unwrap(),
            end_date: NaiveDate::from_ymd_opt(2023, 12, 31).unwrap(),
            duration: Duration::from_millis(5400),
            trace_id: "abc123trace".to_string(),
        })
        .unwrap();

        assert_eq!(report.title, "Economic Overview 2023");
        assert_eq!(report.executive_summary, "The economy performed well.");
        assert_eq!(report.sections.len(), 2);
        assert_eq!(report.indicators_used, vec!["GDP", "UNRATE"]);
        assert_eq!(
            report.time_range_start,
            NaiveDate::from_ymd_opt(2003, 1, 1).unwrap()
        );
        assert_eq!(
            report.time_range_end,
            NaiveDate::from_ymd_opt(2023, 12, 31).unwrap()
        );
        assert_eq!(report.total_data_points, 250);
        assert_eq!(report.total_tokens, 500 + 200 + 800 + 400);
        assert_eq!(report.providers_used, vec!["openai"]);
        assert_eq!(report.generation_duration_ms, 5400);
        assert_eq!(report.trace_id, "abc123trace");
    }
}

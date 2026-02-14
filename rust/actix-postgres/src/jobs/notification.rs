use serde::Deserialize;
use tracing::instrument;

use super::queue::Job;

#[derive(Debug, Deserialize)]
pub struct NotificationPayload {
    pub article_id: i32,
    pub title: String,
}

pub struct NotificationHandler;

impl NotificationHandler {
    #[instrument(name = "job.notification.handle", skip(job), fields(job_id = job.id))]
    pub async fn handle(job: &Job) -> Result<(), anyhow::Error> {
        let payload: NotificationPayload = serde_json::from_value(job.payload.clone())?;

        tracing::info!(
            article_id = payload.article_id,
            title = %payload.title,
            "Processing notification for new article"
        );

        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

        tracing::info!(
            article_id = payload.article_id,
            "Notification sent successfully"
        );

        Ok(())
    }
}

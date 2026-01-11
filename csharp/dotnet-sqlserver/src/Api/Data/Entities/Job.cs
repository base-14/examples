using System.ComponentModel.DataAnnotations;

namespace Api.Data.Entities;

public class Job
{
    public int Id { get; set; }

    [Required, MaxLength(100)]
    public string Kind { get; set; } = null!;

    [Required]
    public string Payload { get; set; } = null!;

    public string? TraceContext { get; set; }

    [Required, MaxLength(50)]
    public string Status { get; set; } = "pending";

    public string? Error { get; set; }

    public int RetryCount { get; set; } = 0;
    public int MaxRetries { get; set; } = 3;
    public DateTime? NextRetryAt { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? ProcessedAt { get; set; }
}

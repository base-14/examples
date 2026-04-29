using System.Diagnostics;
using System.Text.Json.Serialization;

namespace ArticlesApi.Models;

public class Meta
{
    [JsonPropertyName("trace_id")]
    public string TraceId { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("per_page")]
    public int? PerPage { get; set; }

    [JsonPropertyName("total")]
    public long? Total { get; set; }
}

public class ApiResponse<T>
{
    [JsonPropertyName("data")]
    public T? Data { get; set; }

    [JsonPropertyName("meta")]
    public Meta Meta { get; set; } = new();
}

public class ApiError
{
    [JsonPropertyName("code")]
    public string Code { get; set; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;
}

public class ApiErrorResponse
{
    [JsonPropertyName("error")]
    public ApiError Error { get; set; } = new();

    [JsonPropertyName("meta")]
    public Meta Meta { get; set; } = new();
}

public static class ApiResponseFactory
{
    // Surfacing Activity.Current.TraceId lets callers find the trace in Scout.
    public static ApiResponse<T> Ok<T>(T data, int? page = null, int? perPage = null, long? total = null)
    {
        var traceId = Activity.Current?.TraceId.ToString() ?? string.Empty;
        return new ApiResponse<T>
        {
            Data = data,
            Meta = new Meta
            {
                TraceId = traceId,
                Page = page,
                PerPage = perPage,
                Total = total,
            },
        };
    }

    public static ApiErrorResponse Error(string code, string message)
    {
        var traceId = Activity.Current?.TraceId.ToString() ?? string.Empty;
        return new ApiErrorResponse
        {
            Error = new ApiError { Code = code, Message = message },
            Meta = new Meta { TraceId = traceId },
        };
    }
}

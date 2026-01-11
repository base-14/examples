using System.Diagnostics;

namespace Api.Middleware;

public static class ExceptionMiddleware
{
    public static void UseExceptionHandling(this WebApplication app)
    {
        app.UseExceptionHandler(errorApp =>
        {
            errorApp.Run(async context =>
            {
                var traceId = Activity.Current?.TraceId.ToString();
                context.Response.StatusCode = 500;
                context.Response.ContentType = "application/json";

                await context.Response.WriteAsJsonAsync(new
                {
                    error = "Internal server error",
                    trace_id = traceId
                });
            });
        });
    }
}

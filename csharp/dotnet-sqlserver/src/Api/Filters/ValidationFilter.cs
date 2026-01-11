using System.ComponentModel.DataAnnotations;

namespace Api.Filters;

public class ValidationFilter<T> : IEndpointFilter where T : class
{
    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var argument = context.Arguments.OfType<T>().FirstOrDefault();

        if (argument is null)
        {
            return Results.BadRequest(new { error = "Request body is required" });
        }

        var validationResults = new List<ValidationResult>();
        var validationContext = new ValidationContext(argument);

        if (!Validator.TryValidateObject(argument, validationContext, validationResults, validateAllProperties: true))
        {
            var errors = validationResults
                .Where(r => r.ErrorMessage is not null)
                .ToDictionary(
                    r => r.MemberNames.FirstOrDefault() ?? "unknown",
                    r => r.ErrorMessage!);

            return Results.BadRequest(new { errors });
        }

        return await next(context);
    }
}

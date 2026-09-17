using System.Diagnostics;

namespace AgentRebooking.Tests.Support;

/// <summary>
/// Probes for a reachable Docker daemon once per test run and caches the result. Never
/// driven by an environment variable -- a machine with Docker down always gets a real
/// "no" from the daemon itself, so a skipped suite can never be made to look green by
/// setting a flag.
/// </summary>
internal static class DockerProbe
{
    private static readonly Lazy<string?> UnavailableReasonLazy = new(Probe);

    public static bool IsAvailable => UnavailableReasonLazy.Value is null;

    public static string UnavailableReason =>
        UnavailableReasonLazy.Value ?? "Docker is available.";

    private static string? Probe()
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = "docker",
                ArgumentList = { "info", "--format", "{{.ServerVersion}}" },
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            });

            if (process is null)
            {
                return "the docker CLI could not be started";
            }

            if (!process.WaitForExit(5000))
            {
                process.Kill(entireProcessTree: true);
                return "docker info did not respond within 5s -- the daemon is likely down";
            }

            if (process.ExitCode != 0)
            {
                var stderr = process.StandardError.ReadToEnd().Trim();
                return $"docker info exited {process.ExitCode}: {stderr}";
            }

            return null;
        }
        catch (Exception ex)
        {
            return $"the docker CLI probe failed: {ex.Message}";
        }
    }
}

/// <summary>
/// An xUnit <see cref="FactAttribute"/> that skips at runtime, with a reason, when
/// <see cref="DockerProbe"/> finds no reachable Docker daemon. Tests using this attribute
/// stand up a real Postgres via Testcontainers and must run unmodified the moment Docker
/// returns.
/// </summary>
internal sealed class DockerRequiredFactAttribute : FactAttribute
{
    public DockerRequiredFactAttribute()
    {
        if (!DockerProbe.IsAvailable)
        {
            Skip = $"Docker is not reachable ({DockerProbe.UnavailableReason}); this test needs a real Postgres container.";
        }
    }
}

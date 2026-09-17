using System.ComponentModel;
using System.Diagnostics;
using System.IO.Pipelines;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;
using OllamaSharp;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

internal static class Spike
{
    private const string Model = "qwen3.5:9b";
    private const string OllamaUrl = "http://localhost:11434";
    internal static readonly ActivitySource AppSource = new("AgentRebooking");
    internal static readonly System.Diagnostics.Stopwatch Clock = System.Diagnostics.Stopwatch.StartNew();

    private const string Prompt =
        "My booking is BK-1001 and my flight to Berlin was cancelled. Please rebook me on the cheapest alternative.";

    private static async Task<int> Main(string[] args)
    {
        var runLabel = args.Length > 0 ? args[0] : "1";
        var outDir = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "out");
        Directory.CreateDirectory(outDir);
        SpanRecorder.OutPath = Path.GetFullPath(Path.Combine(outDir, $"spans-run{runLabel}.jsonl"));
        var notesPath = Path.GetFullPath(Path.Combine(outDir, $"notes-run{runLabel}.txt"));
        Note.Path = notesPath;
        File.WriteAllText(SpanRecorder.OutPath, "");
        File.WriteAllText(notesPath, "");

        Note.W($"== run {runLabel} at {DateTimeOffset.UtcNow:O} ==");
        Note.W($"HandoffWorkflowBuilderCore.FunctionPrefix = {DumpFunctionPrefix()}");

        var minimal = Environment.GetEnvironmentVariable("SPIKE_MINIMAL_SOURCES") == "1";
        var noMcpSource = Environment.GetEnvironmentVariable("SPIKE_NO_MCP_SOURCE") == "1";
        Note.W($"minimal source set = {minimal}, mcp source dropped = {noMcpSource}");
        var resource = ResourceBuilder.CreateDefault().AddService("agent-rebooking-spike");
        var tb = Sdk.CreateTracerProviderBuilder()
            .SetResourceBuilder(resource)
            .AddSource("Experimental.Microsoft.Agents.AI")
            .AddSource("AgentRebooking");
        if (!noMcpSource)
        {
            tb.AddSource("Experimental.ModelContextProtocol");
        }
        if (!minimal)
        {
            tb.AddSource("Microsoft.Agents.AI.Workflows")
              .AddSource("Experimental.Microsoft.Extensions.AI")
              .AddSource("ModelContextProtocol");
        }
        using var tracer = tb.AddProcessor(new SpanRecorder()).Build();
        using var meter = Sdk.CreateMeterProviderBuilder()
            .SetResourceBuilder(resource)
            .AddMeter("Experimental.Microsoft.Agents.AI")
            .AddMeter("Microsoft.Agents.AI.Workflows")
            .AddMeter("Experimental.Microsoft.Extensions.AI")
            .AddMeter("Experimental.ModelContextProtocol")
            .AddMeter("ModelContextProtocol")
            .AddReader(new PeriodicExportingMetricReader(new MetricNameExporter()) { })
            .Build();

        var sw = Stopwatch.StartNew();
        var exitCode = 0;
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(10));
            using var root = AppSource.StartActivity("spike.run", ActivityKind.Server);
            Note.W($"root span = {root?.SpanId} trace = {root?.TraceId}");
            await RunOnceAsync(cts.Token);
        }
        catch (Exception ex)
        {
            Note.W($"FAILED: {ex.GetType().FullName}: {ex.Message}");
            Note.W(ex.StackTrace ?? "");
            exitCode = 1;
        }
        sw.Stop();
        Note.W($"wall_clock_seconds = {sw.Elapsed.TotalSeconds:F1}");
        tracer.ForceFlush(5000);
        meter.ForceFlush(5000);
        Note.W($"METERS = {string.Join(", ", MetricNameExporter.Seen.OrderBy(x => x))}");
        return exitCode;
    }

    private static string DumpFunctionPrefix()
    {
        var t = typeof(AgentWorkflowBuilder).Assembly
            .GetType("Microsoft.Agents.AI.Workflows.HandoffWorkflowBuilderCore`1");
        var f = t?.GetField("FunctionPrefix", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        return f?.GetRawConstantValue()?.ToString() ?? "<not found>";
    }

    private static async Task RunOnceAsync(CancellationToken ct)
    {
        // ---- in-process MCP server over two pipes ----
        var clientToServer = new Pipe();
        var serverToClient = new Pipe();

        var builder = Host.CreateApplicationBuilder();
        builder.Logging.ClearProviders();
        builder.Services
            .AddMcpServer(o => o.ServerInfo = new Implementation { Name = "rebooking-tools", Version = "0.1.0" })
            .WithStreamServerTransport(clientToServer.Reader.AsStream(), serverToClient.Writer.AsStream())
            .WithTools<BookingTools>();
        using var host = builder.Build();
        await host.StartAsync(ct);

        var clientTransport = new StreamClientTransport(
            serverInput: clientToServer.Writer.AsStream(),
            serverOutput: serverToClient.Reader.AsStream());
        await using var mcpClient = await McpClient.CreateAsync(clientTransport, cancellationToken: ct);
        var mcpTools = await mcpClient.ListToolsAsync(cancellationToken: ct);
        Note.W($"MCP tools = {string.Join(", ", mcpTools.Select(t => t.Name))}");

        var tools = new List<AITool>();
        foreach (var t in mcpTools)
        {
            tools.Add(t.Name == "rebook" ? new ApprovalRequiredAIFunction(t) : t);
        }

        // ---- chat client ----
        var ollama = new OllamaApiClient(new Uri(OllamaUrl), Model);

        var triage = new ChatClientAgent(
                ollama,
                new ChatClientAgentOptions
                {
                    Id = "triage",
                    Name = "triage",
                    Description = "Classifies traveller messages.",
                    ChatOptions = new ChatOptions
                    {
                        Instructions =
                            "You are a travel triage agent. For any message about a cancelled or delayed flight, " +
                            "immediately hand off to the rebooking agent by calling the handoff tool. Do not answer yourself.",
                    },
                })
            .AsBuilder().UseOpenTelemetry().Build();

        var rebooking = new ChatClientAgent(
                ollama,
                new ChatClientAgentOptions
                {
                    Id = "rebooking",
                    Name = "rebooking",
                    Description = "Rebooks travellers onto new flights.",
                    ChatOptions = new ChatOptions
                    {
                        Instructions =
                            "You are a rebooking agent. Call lookup_booking with the booking reference, then call rebook " +
                            "with the booking reference and the cheapest alternative flight id. Then tell the traveller what you did.",
                        Tools = tools,
                    },
                })
            .AsBuilder().UseOpenTelemetry().Build();

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(triage)
            .WithHandoff(triage, rebooking)
            .EmitAgentResponseEvents()
            .Build();

        var input = new List<ChatMessage> { new(ChatRole.User, Prompt) };
        await using var run = await InProcessExecution.RunStreamingAsync(workflow, input, cancellationToken: ct);

        var handled = 0;
        var loops = 0;
        while (loops++ < 20)
        {
            var status = await run.GetStatusAsync(ct);
            Note.W($"-- watch loop {loops}, status = {status}");
            if (status is RunStatus.Ended) break;
            if (loops == 1) await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

            var sawAnything = false;
            await foreach (var evt in run.WatchStreamAsync(blockOnPendingRequest: false, cancellationToken: ct))
            {
                sawAnything = true;
                switch (evt)
                {
                    case RequestInfoEvent rie:
                        Note.W("EVENT RequestInfoEvent");
                        Note.W($"  event type      = {rie.GetType().FullName}");
                        Note.W($"  port id         = {rie.Request.PortInfo.PortId}");
                        Note.W($"  port request T  = {rie.Request.PortInfo.RequestType}");
                        Note.W($"  port response T = {rie.Request.PortInfo.ResponseType}");
                        Note.W($"  request id      = {rie.Request.RequestId}");
                        var viaTryGet = rie.Request.TryGetDataAs<ToolApprovalRequestContent>(out var typed);
                        Note.W($"  TryGetDataAs<ToolApprovalRequestContent> = {viaTryGet}, value null = {typed is null}");
                        var data = Unwrap(rie.Request.Data);
                        Note.W($"  data type       = {data?.GetType().FullName}");
                        DumpMembers("  data", data);
                        var response = BuildApproval(rie, data);
                        if (response is not null)
                        {
                            await run.SendResponseAsync(response);
                            handled++;
                            Note.W($"  -> SendResponseAsync(approved: true) sent at {Clock.Elapsed.TotalSeconds:F1}s");
                        }
                        break;
                    case AgentResponseEvent are:
                        Note.W($"EVENT AgentResponseEvent from {are.ExecutorId}: text={Trunc(are.Response?.Text, 160)}");
                        foreach (var m in are.Response?.Messages ?? new List<ChatMessage>())
                        {
                            foreach (var c in m.Contents)
                            {
                                if (c is FunctionCallContent call)
                                {
                                    Note.W($"    tool call {call.Name} args={JsonSerializer.Serialize(call.Arguments)}");
                                }
                            }
                        }
                        break;
                    case WorkflowOutputEvent oe:
                        if (!oe.IsIntermediate())
                        {
                            Note.W($"EVENT WorkflowOutputEvent from {oe.ExecutorId}: {Trunc(oe.Data?.ToString(), 200)}");
                        }
                        break;
                    case ExecutorFailedEvent fe:
                        Note.W($"EVENT ExecutorFailedEvent {fe.ExecutorId}: {fe.Data}");
                        break;
                    case WorkflowErrorEvent we:
                        Note.W($"EVENT WorkflowErrorEvent: {we.Data}");
                        break;
                    default:
                        Note.W($"EVENT {evt.GetType().Name}: {Trunc(evt.ToString(), 160)}");
                        break;
                }
            }
            var after = await run.GetStatusAsync(ct);
            Note.W($"-- stream drained, status = {after}, sawAnything = {sawAnything}");
            if (after is RunStatus.Ended or RunStatus.Idle) break;
            if (!sawAnything && after is not RunStatus.PendingRequests) break;
        }
        Note.W($"approvals handled = {handled}");
    }

    private static ExternalResponse? BuildApproval(RequestInfoEvent rie, object? data)
    {
        if (data is IExternalRequestEnvelope env)
        {
            var inner = env.GetInnerRequestContent();
            Note.W($"  envelope inner  = {inner?.GetType().FullName}");
            if (inner is ToolApprovalRequestContent tarc)
            {
                Note.W($"  tool call id    = {tarc.ToolCall.CallId}");
                Note.W($"  tool call type  = {tarc.ToolCall.GetType().FullName}");
                if (tarc.ToolCall is FunctionCallContent fcc)
                {
                    Note.W($"  tool call name  = {fcc.Name}");
                    Note.W($"  tool call args  = {JsonSerializer.Serialize(fcc.Arguments)}");
                }
                DumpMembers("  approval", tarc);
                var approval = tarc.CreateResponse(approved: true);
                Note.W($"  approval reply  = {approval.GetType().FullName}");
                var payload = env.CreateResponse(
                    new List<ChatMessage> { new(ChatRole.User, new AIContent[] { approval }) });
                Note.W($"  envelope reply  = {payload?.GetType().FullName}");
                return rie.Request.CreateResponse(payload!);
            }
        }

        if (data is ToolApprovalRequestContent bare)
        {
            Note.W("  data IS a bare ToolApprovalRequestContent (no envelope)");
            Note.W($"  tool call type  = {bare.ToolCall.GetType().FullName}");
            Note.W($"  tool call id    = {bare.ToolCall.CallId}");
            if (bare.ToolCall is FunctionCallContent f)
            {
                Note.W($"  tool call name  = {f.Name}");
                Note.W($"  tool call args  = {JsonSerializer.Serialize(f.Arguments)}");
            }
            var reply = bare.CreateResponse(approved: true);
            Note.W($"  reply type      = {reply.GetType().FullName}");
            Note.W($"  pause_at_s      = {Clock.Elapsed.TotalSeconds:F1}");
            return rie.Request.CreateResponse(reply);
        }

        Note.W("  !! could not build an approval response for this request");
        return null;
    }

    private static object? Unwrap(PortableValue pv)
    {
        var p = typeof(PortableValue).GetProperty("Value",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        return p?.GetValue(pv);
    }

    private static void DumpMembers(string label, object? o)
    {
        if (o is null) return;
        foreach (var p in o.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            object? v;
            try { v = p.GetValue(o); } catch (Exception e) { v = $"<{e.GetType().Name}>"; }
            Note.W($"{label}.{p.Name} ({Short(p.PropertyType)}) = {Trunc(v?.ToString())}");
        }
        foreach (var i in o.GetType().GetInterfaces())
        {
            Note.W($"{label} implements {i.FullName}");
        }
    }

    private static string Short(Type t) => t.Name;

    private static string Trunc(string? s, int n = 300) =>
        s is null ? "<null>" : (s.Length <= n ? s : s[..n] + "...");
}

internal static class Note
{
    public static string Path = "notes.txt";
    public static void W(string s)
    {
        Console.WriteLine(s);
        File.AppendAllText(Path, s + Environment.NewLine);
    }
}

internal sealed class SpanRecorder : BaseProcessor<Activity>
{
    public static string OutPath = "spans.jsonl";
    private static readonly object Gate = new();

    public override void OnEnd(Activity a)
    {
        var tags = new JsonObject();
        foreach (var t in a.TagObjects) tags[t.Key] = JsonValue.Create(t.Value?.ToString());
        var links = new JsonArray();
        foreach (var l in a.Links) links.Add($"{l.Context.TraceId}/{l.Context.SpanId}");
        var o = new JsonObject
        {
            ["source"] = a.Source.Name,
            ["name"] = a.DisplayName,
            ["kind"] = a.Kind.ToString(),
            ["trace_id"] = a.TraceId.ToString(),
            ["span_id"] = a.SpanId.ToString(),
            ["parent_span_id"] = a.ParentSpanId.ToString(),
            ["duration_ms"] = a.Duration.TotalMilliseconds,
            ["status"] = a.Status.ToString(),
            ["tags"] = tags,
            ["links"] = links,
        };
        lock (Gate) File.AppendAllText(OutPath, o.ToJsonString() + Environment.NewLine);
    }
}

internal sealed class MetricNameExporter : BaseExporter<Metric>
{
    public static readonly HashSet<string> Seen = new();

    public override ExportResult Export(in Batch<Metric> batch)
    {
        foreach (var m in batch) lock (Seen) Seen.Add($"{m.MeterName}:{m.Name}");
        return ExportResult.Success;
    }
}

[McpServerToolType]
internal sealed class BookingTools
{
    [McpServerTool(Name = "lookup_booking")]
    [Description("Look up a booking and its alternative flights by booking reference.")]
    public static string LookupBooking(
        RequestContext<CallToolRequestParams> context,
        [Description("The booking reference, for example BK-1001")] string booking_ref)
    {
        Note.W($"  MCP server saw _meta on lookup_booking = {context.Params?.Meta?.ToJsonString() ?? "<null>"}");
        Note.W($"  MCP server Activity.Current = {Activity.Current?.DisplayName} " +
               $"(source={Activity.Current?.Source.Name}, span={Activity.Current?.SpanId}, parent={Activity.Current?.ParentSpanId})");
        return """
               {"booking_ref":"BK-1001","route":"LHR-BER","date":"2026-10-02",
                "alternatives":[{"flight_id":"FL-201","price":180},{"flight_id":"FL-202","price":240}]}
               """;
    }

    [McpServerTool(Name = "rebook")]
    [Description("Rebook the traveller onto the given flight id.")]
    public static string Rebook(
        RequestContext<CallToolRequestParams> context,
        [Description("The booking reference")] string booking_ref,
        [Description("The flight id to rebook onto")] string flight_id)
    {
        Note.W($"  MCP server saw _meta on rebook = {context.Params?.Meta?.ToJsonString() ?? "<null>"}");
        return $"{{\"booking_ref\":\"{booking_ref}\",\"rebooked_to\":\"{flight_id}\",\"status\":\"confirmed\"}}";
    }
}

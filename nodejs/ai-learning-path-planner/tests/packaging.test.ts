import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { loadConfig } from "../src/config.ts";

function read(name: string): string {
  return readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
}

function composeAppEnvironment(): Record<string, string> {
  const compose = parse(read("compose.yaml")) as {
    services: { app: { environment: Record<string, string> } };
  };
  return compose.services.app.environment;
}

// Reads NAME=value lines, ignoring comments and blanks. .env.example is documentation
// that is also a file Compose will read if it is copied to .env, so the values in it are
// the ones a reader actually runs with.
function envExample(): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of read(".env.example").split("\n")) {
    const match = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (match?.[1] !== undefined) {
      values[match[1]] = match[2] ?? "";
    }
  }
  return values;
}

// Compose writes defaults as ${NAME:-default}. This pulls the default back out, so a
// test can compare it with the default the service itself applies.
function composeDefault(value: string): string {
  const match = /^\$\{[A-Z0-9_]+:-(.*)\}$/.exec(value);
  return match?.[1] ?? value;
}

// The provider appends its paths straight onto this value, so a base URL without the /api
// suffix 404s every model call, and the host it names differs by side: the service defaults to
// the host form and compose.yaml overrides it with the container form.
describe("the Ollama base URL reaches Ollama from the host and from the container", () => {
  it("defaults to the host form in src/config.ts, with the /api suffix", () => {
    expect(loadConfig({}).ollamaBaseUrl).toBe("http://localhost:11434/api");
  });

  it("carries the container form in compose.yaml, with the same suffix", () => {
    const composed = composeDefault(composeAppEnvironment().OLLAMA_BASE_URL ?? "");

    expect(composed).toBe("http://host.docker.internal:11434/api");
    expect(composed.endsWith("/api")).toBe(true);
  });

  it("leaves OLLAMA_BASE_URL unset in .env.example, so neither default is overridden", () => {
    // .env.example is documentation that Compose will read if it is copied to .env. A
    // value here would override the container default and break the container, so both
    // forms are documented in the comment above it and the variable itself is left empty.
    expect(envExample().OLLAMA_BASE_URL).toBe("");
    expect(read(".env.example")).toContain("http://localhost:11434/api");
    expect(read(".env.example")).toContain("http://host.docker.internal:11434/api");
  });
});

// The runtime image needs three things to do anything useful: the price table, the corpus
// artifact, and the --import that loads the telemetry SDK before the app's first import. A
// container silently emitting no telemetry makes every verification against it meaningless.
describe("the runtime image carries what the service reads at runtime", () => {
  const dockerfile = read("Dockerfile");

  it("starts the app with the telemetry module imported", () => {
    expect(dockerfile).toMatch(/CMD \[.*"--import".*"\.\/dist\/telemetry\.js".*\]/);
  });

  it("copies the corpus artifact the store loads at boot", () => {
    expect(dockerfile).toMatch(/COPY .*\/app\/data \.\/data/);
  });

  it("copies the price table cost.ts resolves at /_shared/pricing.json", () => {
    expect(dockerfile).toMatch(/COPY --from=shared pricing\.json \/_shared\/pricing\.json/);
  });

  it("declares the named build context the price table comes from", () => {
    const compose = parse(read("compose.yaml")) as {
      services: { app: { build: { additional_contexts?: Record<string, string> } } };
    };
    expect(compose.services.app.build.additional_contexts?.shared).toBe("../../_shared");
  });
});

// F18. Someone who clones this repo has no base14 tenant, and the collector used to exit
// at startup without one, which took the whole stack down with it. The local half of the
// collector configuration now stands alone and the Scout half is a second --config that
// compose.yaml adds only when SCOUT_CLIENT_ID is set. These hold that split in place:
// putting the exporter or the extension back into the local file, or dropping the gate
// from the command, would put the credentials back on the critical path.
describe("the collector starts without base14 credentials", () => {
  const local = parse(read("config/otel-collector.yaml")) as {
    extensions: Record<string, unknown>;
    exporters: Record<string, unknown>;
    service: { extensions: string[]; pipelines: Record<string, { exporters: string[] }> };
  };
  const scout = parse(read("config/otel-collector-scout.yaml")) as {
    extensions: Record<string, unknown>;
    exporters: Record<string, unknown>;
    service: { extensions: string[]; pipelines: Record<string, { exporters: string[] }> };
  };

  it("names no credentialed component in the file that is always loaded", () => {
    expect(Object.keys(local.extensions)).not.toContain("oauth2client");
    expect(Object.keys(local.exporters)).not.toContain("otlp_http/b14");
    expect(local.service.extensions).not.toContain("oauth2client");
    // The comments name the variable; nothing in the file reads it.
    // biome-ignore lint/suspicious/noTemplateCurlyInString: this is collector YAML syntax, not a template literal.
    expect(read("config/otel-collector.yaml")).not.toContain("${env:SCOUT_CLIENT_ID}");
  });

  it("exports every pipeline to debug alone, which is what make verify reads", () => {
    for (const pipeline of Object.values(local.service.pipelines)) {
      expect(pipeline.exporters).toEqual(["debug"]);
    }
  });

  it("keeps the Scout exporter in the second file, on every pipeline", () => {
    expect(Object.keys(scout.extensions)).toContain("oauth2client");
    for (const pipeline of Object.values(scout.service.pipelines)) {
      expect(pipeline.exporters).toEqual(["otlp_http/b14", "debug"]);
    }
  });

  it("adds that file to the collector's command only when SCOUT_CLIENT_ID is set", () => {
    const compose = parse(read("compose.yaml")) as {
      services: { "otel-collector": { command: string; volumes: string[] } };
    };
    const command = compose.services["otel-collector"].command;

    expect(command).toContain("--config=/etc/otel-collector.yaml");
    // biome-ignore lint/suspicious/noTemplateCurlyInString: this is Compose interpolation syntax, not a template literal.
    expect(command).toContain("${SCOUT_CLIENT_ID:+--config=/etc/otel-collector-scout.yaml}");
    // Both files have to be mounted, or the credentialed form starts against a path that
    // is not there.
    expect(compose.services["otel-collector"].volumes).toContain(
      "./config/otel-collector-scout.yaml:/etc/otel-collector-scout.yaml:ro",
    );
  });

  it("leaves all four credentials empty in compose, so none is half set by default", () => {
    const compose = parse(read("compose.yaml")) as {
      services: { "otel-collector": { environment: Record<string, string> } };
    };
    const env = compose.services["otel-collector"].environment;

    for (const name of [
      "SCOUT_ENDPOINT",
      "SCOUT_CLIENT_ID",
      "SCOUT_CLIENT_SECRET",
      "SCOUT_TOKEN_URL",
    ]) {
      expect(composeDefault(env[name] ?? "")).toBe("");
      expect(envExample()[name]).toBe("");
    }
  });
});

// The Hono server span is named for its method alone, so a filter on the span name can never
// match /health and Compose's healthcheck spans export continuously. This filters url.path.
describe("the healthcheck spans the README says are filtered are filtered", () => {
  it("matches the request path attribute, not the span name", () => {
    const local = parse(read("config/otel-collector.yaml")) as {
      processors: { "filter/noisy": { traces: { span: string[] } } };
    };
    const conditions = local.processors["filter/noisy"].traces.span;

    expect(conditions).toContain('attributes["url.path"] == "/health"');
    for (const condition of conditions) {
      expect(condition).not.toContain("IsMatch(name");
    }
  });

  it("runs that filter in the traces pipeline, ahead of the exporters", () => {
    const local = parse(read("config/otel-collector.yaml")) as {
      service: { pipelines: { traces: { processors: string[] } } };
    };
    expect(local.service.pipelines.traces.processors).toContain("filter/noisy");
  });
});

import "../lib/env.js";

let sdk;

const disabledDatabaseUserInstrumentations = Object.fromEntries(
  [
    "cassandra-driver",
    "knex",
    "mongoose",
    "mysql",
    "mysql2",
    "oracledb",
    "pg",
    "tedious",
  ].map((name) => [
    `@opentelemetry/instrumentation-${name}`,
    { enabled: false },
  ]),
);

function isTracingDisabled() {
  return ["1", "true", "yes"].includes(
    String(process.env.OTEL_SDK_DISABLED || "false").toLowerCase(),
  );
}

export async function startTracing() {
  if (isTracingDisabled() || !process.env.OTEL_EXPORTER_OTLP_ENDPOINT) {
    return null;
  }

  const [
    { OTLPTraceExporter },
    { resourceFromAttributes },
    { NodeSDK },
    { getNodeAutoInstrumentations },
  ] = await Promise.all([
    import("@opentelemetry/exporter-trace-otlp-grpc"),
    import("@opentelemetry/resources"),
    import("@opentelemetry/sdk-node"),
    import("@opentelemetry/auto-instrumentations-node"),
  ]);

  sdk = new NodeSDK({
    resource: resourceFromAttributes({
      "service.name":
        process.env.OTEL_SERVICE_NAME ||
        process.env.SERVICE_NAME ||
        "chat-service",

      "service.version": process.env.SERVICE_VERSION || "local",

      "deployment.environment":
        process.env.APP_ENV || process.env.NODE_ENV || "development",
    }),
    traceExporter: new OTLPTraceExporter(),
    instrumentations: [
      getNodeAutoInstrumentations(disabledDatabaseUserInstrumentations),
    ],
  });

  sdk.start();
  console.log("OpenTelemetry tracing enabled for chat-service");

  return sdk;
}

export async function shutdownTracing() {
  if (!sdk) {
    return;
  }

  await sdk.shutdown();
}

await startTracing();

/** Where a provider is reached and what it is called in telemetry. */
export interface ProviderTarget {
  /** `gen_ai.provider.name`. The config key `google` maps to `gcp.gemini` here. */
  semconvName: string;
  serverAddress: string;
  serverPort: number;
}

export interface ModelPricing {
  inputCostPerMToken: number;
  outputCostPerMToken: number;
}

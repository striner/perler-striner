import type { GridSource, RgbaGrid } from "./grid";
import { prepareLocalGrid } from "./grid";

export interface ProcessorConfig {
  baseUrl: string;
  algorithm: string;
  algorithmVersion?: string;
  algorithmParams: Record<string, unknown>;
  timeoutMs: number;
}

interface ProcessorEnvironment {
  PUBLIC_PROCESSOR_API_URL?: string;
  PUBLIC_PROCESSOR_ALGORITHM?: string;
  PUBLIC_PROCESSOR_ALGORITHM_VERSION?: string;
  PUBLIC_PROCESSOR_ALGORITHM_PARAMS?: string;
  PUBLIC_PROCESSOR_TIMEOUT_MS?: string;
}

interface AcquireGridOptions {
  source: GridSource;
  file: File | null;
  width: number;
  height: number;
  config: ProcessorConfig | null;
  signal: AbortSignal;
  fetchImpl?: typeof fetch;
  localProcessor?: typeof prepareLocalGrid;
}

const IDENTIFIER_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/;
const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/;
const BASE64_PATTERN = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

export function readProcessorConfig(env: ProcessorEnvironment): ProcessorConfig | null {
  const baseUrl = env.PUBLIC_PROCESSOR_API_URL?.trim();
  const algorithm = env.PUBLIC_PROCESSOR_ALGORITHM?.trim();
  if (!baseUrl || !algorithm || !IDENTIFIER_PATTERN.test(algorithm)) return null;

  const algorithmVersion = env.PUBLIC_PROCESSOR_ALGORITHM_VERSION?.trim() || undefined;
  if (algorithmVersion && !VERSION_PATTERN.test(algorithmVersion)) return null;

  let algorithmParams: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(env.PUBLIC_PROCESSOR_ALGORITHM_PARAMS || "{}");
    if (!isPlainObject(parsed) || containsBackgroundControl(parsed)) return null;
    algorithmParams = parsed;
  } catch {
    return null;
  }

  const requestedTimeout = Number(env.PUBLIC_PROCESSOR_TIMEOUT_MS || "8000");
  const timeoutMs = Number.isFinite(requestedTimeout)
    ? Math.min(60_000, Math.max(250, Math.round(requestedTimeout)))
    : 8_000;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    algorithm,
    algorithmVersion,
    algorithmParams,
    timeoutMs,
  };
}

export async function acquireGrid(options: AcquireGridOptions): Promise<RgbaGrid> {
  const localProcessor = options.localProcessor ?? prepareLocalGrid;
  if (options.file && options.config && !options.signal.aborted) {
    const remote = await requestBackendGrid(
      options.file,
      options.width,
      options.height,
      options.config,
      options.signal,
      options.fetchImpl
    );
    if (remote) return remote;
    if (options.signal.aborted) throw new DOMException("Request aborted", "AbortError");
  }
  if (options.signal.aborted) throw new DOMException("Request aborted", "AbortError");
  return localProcessor(options.source, options.width, options.height);
}

export async function requestBackendGrid(
  file: File,
  width: number,
  height: number,
  config: ProcessorConfig,
  signal: AbortSignal,
  fetchImpl: typeof fetch = fetch
): Promise<RgbaGrid | null> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal.aborted) return null;
  signal.addEventListener("abort", abort, { once: true });
  const timeout = globalThis.setTimeout(abort, config.timeoutMs);

  try {
    const body = new FormData();
    body.set("image", file, file.name);
    body.set("width", String(width));
    body.set("height", String(height));
    body.set("algorithm", config.algorithm);
    if (config.algorithmVersion) body.set("algorithm_version", config.algorithmVersion);
    body.set("algorithm_params", JSON.stringify(config.algorithmParams));

    const response = await fetchImpl(`${config.baseUrl}/api/v1/process`, {
      method: "POST",
      body,
      signal: controller.signal,
    });
    if (!response.ok) return null;
    return parseGridEnvelope(await response.json(), width, height, config);
  } catch {
    return null;
  } finally {
    globalThis.clearTimeout(timeout);
    signal.removeEventListener("abort", abort);
  }
}

export function parseGridEnvelope(
  payload: unknown,
  expectedWidth: number,
  expectedHeight: number,
  config: Pick<ProcessorConfig, "algorithm" | "algorithmVersion">
): RgbaGrid | null {
  if (!isPlainObject(payload)) return null;
  if (payload.code !== 200 || typeof payload.msg !== "string" || payload.exec !== null) {
    return null;
  }
  if (!isPlainObject(payload.meta)) return null;
  if (
    typeof payload.meta.accept_id !== "string" ||
    !payload.meta.accept_id ||
    typeof payload.meta.perf_time_use !== "number" ||
    !Number.isFinite(payload.meta.perf_time_use) ||
    payload.meta.perf_time_use < 0
  ) {
    return null;
  }

  const data = payload.data;
  if (!isPlainObject(data) || data.version !== 1) return null;
  if (data.width !== expectedWidth || data.height !== expectedHeight) return null;
  if (!isPlainObject(data.algorithm)) return null;
  if (data.algorithm.id !== config.algorithm || typeof data.algorithm.version !== "string") {
    return null;
  }
  if (config.algorithmVersion && data.algorithm.version !== config.algorithmVersion) return null;
  if (typeof data.rgba_base64 !== "string") return null;

  const bytes = decodeBase64(data.rgba_base64);
  if (!bytes || bytes.length !== expectedWidth * expectedHeight * 4) return null;
  return { width: expectedWidth, height: expectedHeight, data: new Uint8ClampedArray(bytes) };
}

function decodeBase64(value: string): Uint8Array | null {
  if (!value || value.length % 4 !== 0 || !BASE64_PATTERN.test(value)) return null;
  try {
    const binary = atob(value);
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  } catch {
    return null;
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function containsBackgroundControl(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsBackgroundControl);
  if (!isPlainObject(value)) return false;
  return Object.entries(value).some(([key, nested]) => {
    const normalized = key.replaceAll("_", "").replaceAll("-", "").toLowerCase();
    return (
      normalized === "removebackground" ||
      normalized === "backgroundremoval" ||
      containsBackgroundControl(nested)
    );
  });
}

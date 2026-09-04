import type { GridSource, RgbaGrid } from "./grid";
import { prepareLocalGrid } from "./grid";

export interface ProcessorConfig {
  baseUrl: string;
  algorithm: string;
  algorithmVersion?: string;
  algorithmParams: Record<string, unknown>;
  timeoutMs: number;
}

export type ProcessingMode = "cv_native" | "tiny_model" | "browser_native";

export interface ProcessorCapability {
  id: string;
  version: string;
  available: boolean;
  unavailableReason: string | null;
}

export interface AnalysisBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AnalysisObject {
  id: string;
  typeId: number;
  typeNameEn: string;
  confidence: number;
  salience: number;
  bbox: AnalysisBox;
}

export interface TinyModelAnalysis {
  analysisToken: string;
  imageWidth: number;
  imageHeight: number;
  objects: AnalysisObject[];
}

export const DEFAULT_TINY_MODEL_MAX_COLORS = 16;
export const MIN_TINY_MODEL_MAX_COLORS = 4;
export const MAX_TINY_MODEL_MAX_COLORS = 20;

export interface CvNativeHyperparameters {
  edgeStrength: number;
  outlineStrength: number;
  backgroundRecoveryDistance: number;
  coarseSubjectCount: number;
  protectionScale: number;
  foregroundSeedDistance: number;
  edgeSeedThreshold: number;
  saturationSeedThreshold: number;
  protectionDilationRadius: number;
  recoveryNeighborhoodRatio: number;
  foregroundCoverageThreshold: number;
}

export const DEFAULT_CV_NATIVE_HYPERPARAMETERS: CvNativeHyperparameters = {
  edgeStrength: 0.65,
  outlineStrength: 0.1,
  backgroundRecoveryDistance: 6,
  coarseSubjectCount: 1,
  protectionScale: 2,
  foregroundSeedDistance: 28,
  edgeSeedThreshold: 56,
  saturationSeedThreshold: 18,
  protectionDilationRadius: 2,
  recoveryNeighborhoodRatio: 0.014,
  foregroundCoverageThreshold: 0.2,
};

export function cvNativeAlgorithmParams(
  values: CvNativeHyperparameters
): Record<string, number> {
  return {
    edge_strength: values.edgeStrength,
    outline_strength: values.outlineStrength,
    background_recovery_distance: values.backgroundRecoveryDistance,
    coarse_subject_count: values.coarseSubjectCount,
    protection_scale: values.protectionScale,
    foreground_seed_distance: values.foregroundSeedDistance,
    edge_seed_threshold: values.edgeSeedThreshold,
    saturation_seed_threshold: values.saturationSeedThreshold,
    protection_dilation_radius: values.protectionDilationRadius,
    recovery_neighborhood_ratio: values.recoveryNeighborhoodRatio,
    foreground_coverage_threshold: values.foregroundCoverageThreshold,
  };
}

export function tinyModelAlgorithmParams(
  analysisToken: string,
  selectedObjectIds: string[],
  maxColors: number = DEFAULT_TINY_MODEL_MAX_COLORS
): Record<string, string | string[] | number> {
  return {
    analysis_token: analysisToken,
    selected_object_ids: selectedObjectIds,
    max_colors: maxColors,
  };
}

export type AcquireGridResult =
  | { grid: RgbaGrid; source: "backend"; fellBack: false }
  | { grid: RgbaGrid; source: "browser"; fellBack: boolean };

interface ProcessorEnvironment {
  PUBLIC_PROCESSOR_API_URL?: string;
  PUBLIC_PROCESSOR_ALGORITHM_PARAMS?: string;
  PUBLIC_PROCESSOR_TIMEOUT_MS?: string;
}

interface AcquireGridOptions {
  source: GridSource;
  file: File | null;
  width: number;
  height: number;
  removeBackground?: boolean;
  config: ProcessorConfig | null;
  signal: AbortSignal;
  fetchImpl?: typeof fetch;
  localProcessor?: typeof prepareLocalGrid;
}

const BASE64_PATTERN = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const DEFAULT_PROCESSOR_TIMEOUT_MS = 35_000;
const MAX_PROCESSOR_TIMEOUT_MS = 300_000;

export function readProcessorConfig(env: ProcessorEnvironment): ProcessorConfig | null {
  const baseUrl = env.PUBLIC_PROCESSOR_API_URL?.trim();
  if (!baseUrl) return null;

  let algorithmParams: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(env.PUBLIC_PROCESSOR_ALGORITHM_PARAMS || "{}");
    if (!isPlainObject(parsed) || containsBackgroundControl(parsed)) return null;
    algorithmParams = parsed;
  } catch {
    return null;
  }

  const requestedTimeout = Number(
    env.PUBLIC_PROCESSOR_TIMEOUT_MS || String(DEFAULT_PROCESSOR_TIMEOUT_MS)
  );
  const timeoutMs = Number.isFinite(requestedTimeout)
    ? Math.min(MAX_PROCESSOR_TIMEOUT_MS, Math.max(250, Math.round(requestedTimeout)))
    : DEFAULT_PROCESSOR_TIMEOUT_MS;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    algorithm: "cv_native",
    algorithmVersion: "1.0.0",
    algorithmParams,
    timeoutMs,
  };
}

export async function acquireGrid(options: AcquireGridOptions): Promise<AcquireGridResult> {
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
    if (remote) return { grid: remote, source: "backend", fellBack: false };
    if (options.signal.aborted) throw new DOMException("Request aborted", "AbortError");
  }
  if (options.signal.aborted) throw new DOMException("Request aborted", "AbortError");
  const removeBackground = options.config ? true : (options.removeBackground ?? true);
  return {
    grid: localProcessor(options.source, options.width, options.height, removeBackground),
    source: "browser",
    fellBack: Boolean(options.file && options.config),
  };
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

export async function requestProcessorCapabilities(
  baseUrl: string,
  signal: AbortSignal,
  fetchImpl: typeof fetch = fetch
): Promise<ProcessorCapability[] | null> {
  try {
    const response = await fetchImpl(`${baseUrl.replace(/\/+$/, "")}/api/v1/algorithms`, {
      signal,
    });
    if (!response.ok) return null;
    const payload = await response.json();
    if (!isValidSuccessEnvelope(payload) || !isPlainObject(payload.data)) return null;
    if (!Array.isArray(payload.data.items)) return null;
    const capabilities: ProcessorCapability[] = [];
    for (const item of payload.data.items) {
      if (!isPlainObject(item)) return null;
      if (
        typeof item.id !== "string" ||
        !item.id ||
        typeof item.version !== "string" ||
        !item.version ||
        typeof item.available !== "boolean" ||
        (item.unavailable_reason !== null && typeof item.unavailable_reason !== "string")
      ) {
        return null;
      }
      capabilities.push({
        id: item.id,
        version: item.version,
        available: item.available,
        unavailableReason: item.unavailable_reason,
      });
    }
    return capabilities;
  } catch {
    return null;
  }
}

export async function requestBackendAnalysis(
  file: File,
  config: Pick<ProcessorConfig, "baseUrl" | "algorithm" | "algorithmVersion" | "timeoutMs">,
  signal: AbortSignal,
  fetchImpl: typeof fetch = fetch
): Promise<TinyModelAnalysis | null> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal.aborted) return null;
  signal.addEventListener("abort", abort, { once: true });
  const timeout = globalThis.setTimeout(abort, config.timeoutMs);

  try {
    const body = new FormData();
    body.set("image", file, file.name);
    body.set("algorithm", config.algorithm);
    if (config.algorithmVersion) body.set("algorithm_version", config.algorithmVersion);
    const response = await fetchImpl(`${config.baseUrl}/api/v1/analyze`, {
      method: "POST",
      body,
      signal: controller.signal,
    });
    if (!response.ok) return null;
    return parseAnalysisEnvelope(await response.json(), config);
  } catch {
    return null;
  } finally {
    globalThis.clearTimeout(timeout);
    signal.removeEventListener("abort", abort);
  }
}

export function parseAnalysisEnvelope(
  payload: unknown,
  config: Pick<ProcessorConfig, "algorithm" | "algorithmVersion">
): TinyModelAnalysis | null {
  if (!isValidSuccessEnvelope(payload) || !isPlainObject(payload.data)) return null;
  const data = payload.data;
  if (data.version !== 1 || typeof data.analysis_token !== "string" || !data.analysis_token) {
    return null;
  }
  if (!isPlainObject(data.image) || !isPositiveInteger(data.image.width)) return null;
  if (!isPositiveInteger(data.image.height) || !isPlainObject(data.algorithm)) return null;
  if (data.algorithm.id !== config.algorithm || typeof data.algorithm.version !== "string") {
    return null;
  }
  if (config.algorithmVersion && data.algorithm.version !== config.algorithmVersion) return null;
  if (!Array.isArray(data.objects) || data.objects.length < 1 || data.objects.length > 24) {
    return null;
  }

  const objects: AnalysisObject[] = [];
  const ids = new Set<string>();
  for (const item of data.objects) {
    if (!isPlainObject(item) || !isPlainObject(item.bbox)) return null;
    if (
      typeof item.id !== "string" ||
      !item.id ||
      ids.has(item.id) ||
      !Number.isInteger(item.type_id) ||
      (item.type_id as number) < 0 ||
      typeof item.type_name_en !== "string" ||
      !item.type_name_en ||
      !isUnitNumber(item.confidence) ||
      !isUnitNumber(item.salience) ||
      !isUnitNumber(item.bbox.x) ||
      !isUnitNumber(item.bbox.y) ||
      !isPositiveUnitNumber(item.bbox.width) ||
      !isPositiveUnitNumber(item.bbox.height) ||
      item.bbox.x + item.bbox.width > 1.000001 ||
      item.bbox.y + item.bbox.height > 1.000001
    ) {
      return null;
    }
    ids.add(item.id);
    objects.push({
      id: item.id,
      typeId: item.type_id as number,
      typeNameEn: item.type_name_en,
      confidence: item.confidence,
      salience: item.salience,
      bbox: {
        x: item.bbox.x,
        y: item.bbox.y,
        width: item.bbox.width,
        height: item.bbox.height,
      },
    });
  }
  return {
    analysisToken: data.analysis_token,
    imageWidth: data.image.width,
    imageHeight: data.image.height,
    objects,
  };
}

export function parseGridEnvelope(
  payload: unknown,
  expectedWidth: number,
  expectedHeight: number,
  config: Pick<ProcessorConfig, "algorithm" | "algorithmVersion">
): RgbaGrid | null {
  if (!isValidSuccessEnvelope(payload)) return null;

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

function isValidSuccessEnvelope(
  payload: unknown
): payload is Record<string, unknown> & {
  data: unknown;
  meta: { accept_id: string; perf_time_use: number };
} {
  if (!isPlainObject(payload)) return false;
  if (payload.code !== 200 || typeof payload.msg !== "string" || payload.exec !== null) {
    return false;
  }
  if (!isPlainObject(payload.meta)) return false;
  return (
    typeof payload.meta.accept_id === "string" &&
    Boolean(payload.meta.accept_id) &&
    typeof payload.meta.perf_time_use === "number" &&
    Number.isFinite(payload.meta.perf_time_use) &&
    payload.meta.perf_time_use >= 0
  );
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

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isUnitNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isPositiveUnitNumber(value: unknown): value is number {
  return isUnitNumber(value) && value > 0;
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

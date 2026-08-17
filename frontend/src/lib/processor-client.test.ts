import { describe, expect, it, vi } from "vitest";

import type { GridSource, RgbaGrid } from "./grid";
import {
  acquireGrid,
  cvNativeAlgorithmParams,
  DEFAULT_CV_NATIVE_HYPERPARAMETERS,
  parseGridEnvelope,
  readProcessorConfig,
  requestBackendGrid,
  type ProcessorConfig,
} from "./processor-client";

const config: ProcessorConfig = {
  baseUrl: "https://processor.example",
  algorithm: "subject-grid",
  algorithmVersion: "1.0.0",
  algorithmParams: { quality: "balanced" },
  timeoutMs: 1_000,
};

function base64(bytes: number[]): string {
  return btoa(String.fromCharCode(...bytes));
}

function envelope(overrides: Record<string, unknown> = {}) {
  return {
    code: 200,
    msg: "success",
    data: {
      version: 1,
      width: 1,
      height: 1,
      rgba_base64: base64([10, 20, 30, 255]),
      algorithm: { id: "subject-grid", version: "1.0.0" },
    },
    exec: null,
    meta: { accept_id: "request-id", perf_time_use: 2.5 },
    ...overrides,
  };
}

describe("readProcessorConfig", () => {
  it("requires a URL and defaults to cv_native", () => {
    expect(
      readProcessorConfig({ PUBLIC_PROCESSOR_API_URL: "https://api.example" })
    ).toMatchObject({
      algorithm: "cv_native",
      timeoutMs: 35_000,
    });
    expect(readProcessorConfig({})).toBeNull();
  });

  it("rejects background-removal controls in algorithm params", () => {
    expect(
      readProcessorConfig({
        PUBLIC_PROCESSOR_API_URL: "https://api.example",
        PUBLIC_PROCESSOR_ALGORITHM_PARAMS: '{"nested":{"remove_background":false}}',
      })
    ).toBeNull();
  });
});

describe("cvNativeAlgorithmParams", () => {
  it("maps the complete UI state to the backend snake-case contract", () => {
    expect(cvNativeAlgorithmParams(DEFAULT_CV_NATIVE_HYPERPARAMETERS)).toEqual({
      edge_strength: 0.65,
      outline_strength: 0.1,
      background_recovery_distance: 6,
      coarse_subject_count: 1,
      protection_scale: 2,
      foreground_seed_distance: 28,
      edge_seed_threshold: 56,
      saturation_seed_threshold: 18,
      protection_dilation_radius: 2,
      recovery_neighborhood_ratio: 0.014,
      foreground_coverage_threshold: 0.2,
    });
  });
});

describe("parseGridEnvelope", () => {
  it("decodes a valid grid", () => {
    const grid = parseGridEnvelope(envelope(), 1, 1, config);
    expect(grid).not.toBeNull();
    expect([...grid!.data]).toEqual([10, 20, 30, 255]);
  });

  it.each([
    ["wrong code", envelope({ code: 500 })],
    ["missing message", envelope({ msg: undefined })],
    ["exception on success", envelope({ exec: "RuntimeError" })],
    ["invalid exception type", envelope({ exec: 42 })],
    ["empty request id", envelope({ meta: { accept_id: "", perf_time_use: 1 } })],
    ["negative duration", envelope({ meta: { accept_id: "request-id", perf_time_use: -1 } })],
    ["wrong schema version", envelope({ data: { ...envelope().data, version: 2 } })],
    ["wrong dimensions", envelope({ data: { ...envelope().data, width: 2 } })],
    [
      "wrong algorithm",
      envelope({
        data: {
          ...envelope().data,
          algorithm: { id: "other-grid", version: "1.0.0" },
        },
      }),
    ],
    ["bad base64", envelope({ data: { ...envelope().data, rgba_base64: "%%%=" } })],
    ["wrong byte length", envelope({ data: { ...envelope().data, rgba_base64: "AA==" } })],
  ])("rejects %s", (_name, payload) => {
    expect(parseGridEnvelope(payload, 1, 1, config)).toBeNull();
  });
});

describe("requestBackendGrid", () => {
  it("sends the stable algorithm fields without remove_background", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body as FormData;
      expect(body.get("algorithm")).toBe("subject-grid");
      expect(body.get("algorithm_version")).toBe("1.0.0");
      expect(body.get("algorithm_params")).toBe('{"quality":"balanced"}');
      expect(body.get("remove_background")).toBeNull();
      return new Response(JSON.stringify(envelope()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    const result = await requestBackendGrid(
      new File(["image"], "source.png", { type: "image/png" }),
      1,
      1,
      config,
      new AbortController().signal,
      fetchImpl
    );
    expect(result?.width).toBe(1);
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it("sends exposed cv_native hyperparameters as algorithm_params", async () => {
    const algorithmParams = cvNativeAlgorithmParams(DEFAULT_CV_NATIVE_HYPERPARAMETERS);
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body as FormData;
      expect(JSON.parse(String(body.get("algorithm_params")))).toEqual(algorithmParams);
      return new Response(JSON.stringify(envelope()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;

    await requestBackendGrid(
      new File(["image"], "source.png", { type: "image/png" }),
      1,
      1,
      { ...config, algorithmParams },
      new AbortController().signal,
      fetchImpl
    );
    expect(fetchImpl).toHaveBeenCalledOnce();
  });
});

describe("acquireGrid", () => {
  it("uses the local processor after a backend 501", async () => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray([1, 2, 3, 255]),
    };
    const localProcessor = vi.fn(() => localGrid);
    const fetchImpl = vi.fn(async () => new Response("", { status: 501 })) as typeof fetch;
    const source = { image: {} as CanvasImageSource, width: 10, height: 10 } satisfies GridSource;

    const result = await acquireGrid({
      source,
      file: new File(["image"], "source.png", { type: "image/png" }),
      width: 1,
      height: 1,
      config,
      signal: new AbortController().signal,
      fetchImpl,
      localProcessor,
    });

    expect(result).toEqual({ grid: localGrid, source: "browser", fellBack: true });
    expect(localProcessor).toHaveBeenCalledOnce();
  });

  it("uses the local processor immediately when backend config is absent", async () => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray(4),
    };
    const localProcessor = vi.fn(() => localGrid);
    const result = await acquireGrid({
      source: { image: {} as CanvasImageSource, width: 1, height: 1 },
      file: null,
      width: 1,
      height: 1,
      config: null,
      signal: new AbortController().signal,
      localProcessor,
    });
    expect(result).toEqual({ grid: localGrid, source: "browser", fellBack: false });
  });

  it("passes the browser background preference to local processing", async () => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray(4),
    };
    const source = { image: {} as CanvasImageSource, width: 1, height: 1 };
    const localProcessor = vi.fn(() => localGrid);

    await acquireGrid({
      source,
      file: null,
      width: 1,
      height: 1,
      removeBackground: false,
      config: null,
      signal: new AbortController().signal,
      localProcessor,
    });

    expect(localProcessor).toHaveBeenCalledWith(source, 1, 1, false);
  });

  it("forces background removal for backend fallback", async () => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray(4),
    };
    const source = { image: {} as CanvasImageSource, width: 1, height: 1 };
    const localProcessor = vi.fn(() => localGrid);
    const fetchImpl = vi.fn(async () => new Response("", { status: 501 })) as typeof fetch;

    await acquireGrid({
      source,
      file: new File(["image"], "source.png", { type: "image/png" }),
      width: 1,
      height: 1,
      removeBackground: false,
      config,
      signal: new AbortController().signal,
      fetchImpl,
      localProcessor,
    });

    expect(localProcessor).toHaveBeenCalledWith(source, 1, 1, true);
  });

  it.each([
    ["network error", async () => Promise.reject(new TypeError("offline"))],
    ["empty success body", async () => new Response("", { status: 200 })],
    ["invalid success body", async () => new Response("not-json", { status: 200 })],
  ])("uses the local processor after a %s", async (_name, responseFactory) => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray([4, 3, 2, 255]),
    };
    const localProcessor = vi.fn(() => localGrid);
    const fetchImpl = vi.fn(responseFactory) as typeof fetch;

    const result = await acquireGrid({
      source: { image: {} as CanvasImageSource, width: 1, height: 1 },
      file: new File(["image"], "source.png", { type: "image/png" }),
      width: 1,
      height: 1,
      config,
      signal: new AbortController().signal,
      fetchImpl,
      localProcessor,
    });

    expect(result).toEqual({ grid: localGrid, source: "browser", fellBack: true });
    expect(localProcessor).toHaveBeenCalledOnce();
  });

  it("uses the local processor after a backend timeout", async () => {
    const localGrid: RgbaGrid = {
      width: 1,
      height: 1,
      data: new Uint8ClampedArray([4, 3, 2, 255]),
    };
    const localProcessor = vi.fn(() => localGrid);
    const fetchImpl = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Request aborted", "AbortError"));
        });
      })) as typeof fetch;

    const result = await acquireGrid({
      source: { image: {} as CanvasImageSource, width: 1, height: 1 },
      file: new File(["image"], "source.png", { type: "image/png" }),
      width: 1,
      height: 1,
      config: { ...config, timeoutMs: 5 },
      signal: new AbortController().signal,
      fetchImpl,
      localProcessor,
    });

    expect(result).toEqual({ grid: localGrid, source: "browser", fellBack: true });
    expect(localProcessor).toHaveBeenCalledOnce();
  });

  it("does not run a stale request's local fallback after cancellation", async () => {
    const controller = new AbortController();
    controller.abort();
    const localProcessor = vi.fn();

    await expect(
      acquireGrid({
        source: { image: {} as CanvasImageSource, width: 1, height: 1 },
        file: new File(["image"], "source.png", { type: "image/png" }),
        width: 1,
        height: 1,
        config,
        signal: controller.signal,
        localProcessor,
      })
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(localProcessor).not.toHaveBeenCalled();
  });
});

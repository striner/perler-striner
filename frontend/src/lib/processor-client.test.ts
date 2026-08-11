import { describe, expect, it, vi } from "vitest";

import type { GridSource, RgbaGrid } from "./grid";
import {
  acquireGrid,
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
  it("requires both a URL and an algorithm", () => {
    expect(readProcessorConfig({ PUBLIC_PROCESSOR_API_URL: "https://api.example" })).toBeNull();
    expect(readProcessorConfig({ PUBLIC_PROCESSOR_ALGORITHM: "subject-grid" })).toBeNull();
  });

  it("rejects background-removal controls in algorithm params", () => {
    expect(
      readProcessorConfig({
        PUBLIC_PROCESSOR_API_URL: "https://api.example",
        PUBLIC_PROCESSOR_ALGORITHM: "subject-grid",
        PUBLIC_PROCESSOR_ALGORITHM_PARAMS: '{"nested":{"remove_background":false}}',
      })
    ).toBeNull();
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

    expect(result).toBe(localGrid);
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
    expect(result).toBe(localGrid);
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

    expect(result).toBe(localGrid);
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

    expect(result).toBe(localGrid);
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

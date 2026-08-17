import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Download,
  LoaderCircle,
  RotateCcw,
  WandSparkles,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ui, type Locale } from "@/i18n/ui";
import { type RgbaGrid } from "@/lib/grid";
import { BRANDS, type BrandId } from "@/lib/palette";
import { generatePattern, type Pattern } from "@/lib/pattern";
import {
  acquireGrid,
  cvNativeAlgorithmParams,
  DEFAULT_CV_NATIVE_HYPERPARAMETERS,
  readProcessorConfig,
  requestProcessorCapabilities,
  tinyModelAlgorithmParams,
  validateTinyModelPrompt,
  type CvNativeHyperparameters,
  type ProcessorCapability,
  type ProcessingMode,
} from "@/lib/processor-client";
import { patternRenderSize, renderExport, renderPattern } from "@/lib/render";

interface Source {
  image: CanvasImageSource;
  width: number;
  height: number;
  name: string;
  thumb: string;
  file: File | null;
}

const MAX_BEADS = 150;
const DEFAULT_BEADS = 87;
const PROCESSOR_CONFIG = readProcessorConfig(import.meta.env);

type GenerationState = "empty" | "dirty" | "generating" | "ready";

interface HyperparameterControl {
  key: keyof CvNativeHyperparameters;
  label: string;
  min: number;
  max: number;
  step: number;
  format?: (value: number) => string;
}

// Built-in sample: a little pixel heart so the app demos without an upload.
const HEART = [
  "..RR..RR..",
  ".RRRR.RRRR",
  "RRPRRRRRRR",
  "RPPRRRRRRR",
  "RPRRRRRRRR",
  ".RRRRRRRR.",
  "..RRRRRR..",
  "...RRRR...",
  "....RR....",
];

async function loadImage(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(file, {
        imageOrientation: "from-image",
      });
    } catch {
      // Fall back to HTMLImageElement decoding below.
    }
  }

  const dataUrl = await readFileAsDataUrl(file);
  const img = new Image();
  img.decoding = "async";
  img.src = dataUrl;
  await img.decode();
  return img;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function makeSample(): Source {
  const scale = 20;
  const w = HEART[0]!.length;
  const h = HEART.length;
  const c = document.createElement("canvas");
  c.width = w * scale;
  c.height = h * scale;
  const ctx = c.getContext("2d")!;
  const fills: Record<string, string> = { R: "#C62A34", P: "#F7CAD7" };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const f = fills[HEART[y]![x]!];
      if (!f) continue;
      ctx.fillStyle = f;
      ctx.fillRect(x * scale, y * scale, scale, scale);
    }
  }
  return {
    image: c,
    width: c.width,
    height: c.height,
    name: "sample-heart",
    thumb: c.toDataURL(),
    file: null,
  };
}

export default function PerlerStudio({
  locale = "en",
}: {
  locale?: Locale;
}) {
  const t = ui[locale];
  const [source, setSource] = useState<Source | null>(null);
  const [processingMode, setProcessingMode] =
    useState<ProcessingMode>("browser_native");
  const [fallbackNotice, setFallbackNotice] = useState(0);
  const [subjectPrompt, setSubjectPrompt] = useState("");
  const [processorCapabilities, setProcessorCapabilities] = useState<
    ProcessorCapability[] | null
  >(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(
    Boolean(PROCESSOR_CONFIG)
  );
  const [hyperparameters, setHyperparameters] = useState<CvNativeHyperparameters>(
    DEFAULT_CV_NATIVE_HYPERPARAMETERS
  );
  const [hyperparametersExpanded, setHyperparametersExpanded] = useState(false);
  const [generationState, setGenerationState] = useState<GenerationState>("empty");
  const [brand, setBrand] = useState<BrandId>("mard221");
  const [beadsAcross, setBeadsAcross] = useState(DEFAULT_BEADS);
  const [dither, setDither] = useState(false);
  const [removeBackground, setRemoveBackground] = useState(true);
  const [grid, setGrid] = useState(true);
  const [cell, setCell] = useState(14);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [gridImage, setGridImage] = useState<RgbaGrid | null>(null);
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const fileInputId = useId();

  useEffect(() => {
    if (!fallbackNotice) return;
    const timeout = globalThis.setTimeout(() => setFallbackNotice(0), 5_000);
    return () => globalThis.clearTimeout(timeout);
  }, [fallbackNotice]);

  useEffect(() => {
    return () => requestControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!PROCESSOR_CONFIG) return;
    const controller = new AbortController();
    setCapabilitiesLoading(true);
    void requestProcessorCapabilities(PROCESSOR_CONFIG.baseUrl, controller.signal).then(
      (capabilities) => {
        if (controller.signal.aborted) return;
        setProcessorCapabilities(capabilities);
        setCapabilitiesLoading(false);
      }
    );
    return () => controller.abort();
  }, []);

  const loadFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("image/")) return;
    try {
      const bmp = await loadImage(file);
      setSource((prev) => {
        if (prev?.thumb.startsWith("blob:")) URL.revokeObjectURL(prev.thumb);
        return {
          image: bmp,
          width: bmp.width,
          height: bmp.height,
          name: file.name.replace(/\.[^.]+$/, ""),
          thumb: URL.createObjectURL(file),
          file,
        };
      });
      setHighlight(null);
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      requestIdRef.current += 1;
      setGridImage(null);
      setPattern(null);
      setFallbackNotice(0);
      setGenerationState("dirty");
    } catch {
      // unsupported image format; ignore
    }
  }, []);

  const invalidateGeneration = useCallback(() => {
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    requestIdRef.current += 1;
    setFallbackNotice(0);
    setGridImage(null);
    setPattern(null);
    setGenerationState(source ? "dirty" : "empty");
  }, [source]);

  const tinyModelCapability = processorCapabilities?.find(
    (capability) => capability.id === "tiny_model" && capability.version === "1.0.0"
  );
  const tinyModelAvailable = Boolean(PROCESSOR_CONFIG && tinyModelCapability?.available);
  const tinyModelPromptError = validateTinyModelPrompt(subjectPrompt);
  const tinyModelUnavailableMessage = !PROCESSOR_CONFIG
    ? t.tinyModelNotConfigured
    : capabilitiesLoading
      ? t.tinyModelChecking
      : processorCapabilities === null
        ? t.tinyModelBackendUnavailable
        : !tinyModelCapability
          ? t.tinyModelNotRegistered
          : !tinyModelCapability.available
            ? t.tinyModelUnavailable(
                tinyModelCapability.unavailableReason || t.tinyModelBackendUnavailable
              )
            : null;
  const processingModeLabel =
    processingMode === "cv_native"
      ? t.cvNative
      : processingMode === "tiny_model"
        ? t.tinyModel
        : t.browserNative;

  const generate = useCallback(async () => {
    if (!source || generationState === "generating") return;
    const w = Math.min(beadsAcross, MAX_BEADS);
    const h = Math.max(
      1,
      Math.min(MAX_BEADS, Math.round((w * source.height) / source.width))
    );
    const requestId = ++requestIdRef.current;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    let config = null;
    if (processingMode === "cv_native" && PROCESSOR_CONFIG) {
      config = {
        ...PROCESSOR_CONFIG,
        algorithm: "cv_native",
        algorithmVersion: "1.0.0",
        algorithmParams: {
          ...PROCESSOR_CONFIG.algorithmParams,
          ...cvNativeAlgorithmParams(hyperparameters),
        },
      };
    } else if (processingMode === "tiny_model" && PROCESSOR_CONFIG && tinyModelAvailable) {
      config = {
        ...PROCESSOR_CONFIG,
        algorithm: "tiny_model",
        algorithmVersion: "1.0.0",
        algorithmParams: tinyModelAlgorithmParams(subjectPrompt),
      };
    }

    setFallbackNotice(0);
    setGridImage(null);
    setPattern(null);
    setGenerationState("generating");
    try {
      const result = await acquireGrid({
        source,
        file: source.file,
        width: w,
        height: h,
        removeBackground,
        config,
        signal: controller.signal,
      });
      if (!controller.signal.aborted && requestId === requestIdRef.current) {
        setGridImage(result.grid);
        if (result.fellBack) setFallbackNotice((event) => event + 1);
        else setFallbackNotice(0);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        console.error("Failed to prepare image grid", error);
        setGridImage(null);
        setPattern(null);
        setGenerationState("dirty");
      }
    } finally {
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  }, [
    source,
    generationState,
    beadsAcross,
    processingMode,
    hyperparameters,
    removeBackground,
    subjectPrompt,
    tinyModelAvailable,
  ]);

  // Palette matching and dithering remain entirely in the frontend.
  useEffect(() => {
    if (!gridImage) return;
    const frame = requestAnimationFrame(() => {
      try {
        setPattern(generatePattern(gridImage, { dither, brand }));
        setGenerationState("ready");
      } catch (error) {
        console.error("Failed to generate bead pattern", error);
        setPattern(null);
        setGenerationState("dirty");
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [gridImage, dither, brand]);

  const updateHyperparameter = useCallback(
    (key: keyof CvNativeHyperparameters, value: number) => {
      setHyperparameters((current) => ({ ...current, [key]: value }));
      invalidateGeneration();
    },
    [invalidateGeneration]
  );

  const hyperparametersAreDefault = Object.entries(
    DEFAULT_CV_NATIVE_HYPERPARAMETERS
  ).every(
    ([key, value]) => hyperparameters[key as keyof CvNativeHyperparameters] === value
  );

  const resetHyperparameters = useCallback(() => {
    setHyperparameters({ ...DEFAULT_CV_NATIVE_HYPERPARAMETERS });
    invalidateGeneration();
  }, [invalidateGeneration]);

  const controlsLocked = generationState === "generating";
  const hyperparameterControls: HyperparameterControl[] = [
    {
      key: "backgroundRecoveryDistance",
      label: t.hpBackgroundRecoveryDistance,
      min: 0,
      max: 40,
      step: 1,
    },
    { key: "coarseSubjectCount", label: t.hpCoarseSubjectCount, min: 1, max: 5, step: 1 },
    { key: "protectionScale", label: t.hpProtectionScale, min: 1, max: 4, step: 0.25 },
    {
      key: "foregroundSeedDistance",
      label: t.hpForegroundSeedDistance,
      min: 0,
      max: 80,
      step: 1,
    },
    { key: "edgeSeedThreshold", label: t.hpEdgeSeedThreshold, min: 0, max: 255, step: 1 },
    {
      key: "saturationSeedThreshold",
      label: t.hpSaturationSeedThreshold,
      min: 0,
      max: 255,
      step: 1,
    },
    {
      key: "protectionDilationRadius",
      label: t.hpProtectionDilationRadius,
      min: 0,
      max: 12,
      step: 1,
    },
    {
      key: "recoveryNeighborhoodRatio",
      label: t.hpRecoveryNeighborhood,
      min: 0.002,
      max: 0.05,
      step: 0.001,
      format: (value) => `${(value * 100).toFixed(1)}%`,
    },
    {
      key: "foregroundCoverageThreshold",
      label: t.hpForegroundCoverage,
      min: 0.05,
      max: 0.8,
      step: 0.01,
      format: (value) => `${Math.round(value * 100)}%`,
    },
    { key: "edgeStrength", label: t.hpEdgeStrength, min: 0, max: 1.5, step: 0.05 },
    { key: "outlineStrength", label: t.hpOutlineStrength, min: 0, max: 0.3, step: 0.01 },
  ];

  // Paint the visible canvas.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pattern) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const size = patternRenderSize(pattern, cell);
    canvas.width = size.width * dpr;
    canvas.height = size.height * dpr;
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    renderPattern(ctx, pattern, { cell, grid, highlight });
  }, [pattern, cell, grid, highlight]);

  const download = useCallback(() => {
    if (!pattern || !source) return;
    renderExport(pattern).toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${source.name}-perler-pattern.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }, [pattern, source]);

  const boards = pattern
    ? Math.ceil(pattern.width / 29) * Math.ceil(pattern.height / 29)
    : 0;

  return (
    <div className="relative grid gap-6 lg:grid-cols-[320px_1fr]">
      {fallbackNotice > 0 && (
        <div
          role="status"
          className="fixed bottom-4 right-4 z-50 flex max-w-[calc(100vw-2rem)] items-center gap-3 rounded-md border border-amber-300 bg-background px-4 py-3 text-sm shadow-lg"
        >
          <span>{t.backendFallback}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-7 shrink-0"
            aria-label={t.closeNotice}
            onClick={() => setFallbackNotice(0)}
          >
            <X className="size-4" />
          </Button>
        </div>
      )}
      {/* ---- Controls ---- */}
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t.imageTitle}</CardTitle>
            <CardDescription>{t.imageDesc}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label
              htmlFor={controlsLocked ? undefined : fileInputId}
              tabIndex={controlsLocked ? -1 : 0}
              aria-disabled={controlsLocked}
              onKeyDown={(e) =>
                !controlsLocked &&
                (e.key === "Enter" || e.key === " ") &&
                fileRef.current?.click()
              }
              onDragOver={(e) => {
                e.preventDefault();
                if (controlsLocked) return;
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                if (controlsLocked) return;
                setDragOver(false);
                const f = e.dataTransfer.files[0];
                if (f) void loadFile(f);
              }}
              className={`flex min-h-28 flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 text-center text-sm transition-colors ${
                controlsLocked ? "cursor-not-allowed opacity-50" : "cursor-pointer"
              } ${
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/50"
              }`}
            >
              {source ? (
                <img
                  src={source.thumb}
                  alt={source.name}
                  className="max-h-32 max-w-full rounded border object-contain"
                />
              ) : (
                <>
                  <span className="text-2xl">🖼️</span>
                  <span className="text-muted-foreground">{t.dropHint}</span>
                </>
              )}
            </label>
            <input
              id={fileInputId}
              ref={fileRef}
              type="file"
              disabled={controlsLocked}
              accept="image/*"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void loadFile(f);
                e.target.value = "";
              }}
            />
            <div className="flex gap-2">
              <Button asChild className="flex-1">
                <label
                  htmlFor={controlsLocked ? undefined : fileInputId}
                  aria-disabled={controlsLocked}
                  className={
                    controlsLocked
                      ? "pointer-events-none cursor-not-allowed opacity-50"
                      : "cursor-pointer"
                  }
                >
                  {t.chooseImage}
                </label>
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={controlsLocked}
                onClick={() => {
                  setSource(makeSample());
                  setGridImage(null);
                  setPattern(null);
                  setFallbackNotice(0);
                  setGenerationState("dirty");
                }}
              >
                {t.trySample}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.settingsTitle}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label>{t.processingMode}</Label>
              <Select
                value={processingMode}
                disabled={controlsLocked}
                onValueChange={(value) => {
                  setProcessingMode(value as ProcessingMode);
                  invalidateGeneration();
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{processingModeLabel}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cv_native" disabled={!PROCESSOR_CONFIG}>
                    {t.cvNative}
                  </SelectItem>
                  <SelectItem value="tiny_model" disabled={!tinyModelAvailable}>
                    {t.tinyModel}
                  </SelectItem>
                  <SelectItem value="browser_native">{t.browserNative}</SelectItem>
                </SelectContent>
              </Select>
              {tinyModelUnavailableMessage && (
                <p className="text-xs leading-relaxed text-muted-foreground" role="status">
                  {tinyModelUnavailableMessage}
                </p>
              )}
            </div>
            {processingMode === "tiny_model" && (
              <div className="space-y-2">
                <Label htmlFor="tiny-model-prompt">{t.subjectPrompt}</Label>
                <Textarea
                  id="tiny-model-prompt"
                  value={subjectPrompt}
                  maxLength={520}
                  rows={3}
                  disabled={controlsLocked}
                  placeholder={t.subjectPromptPlaceholder}
                  aria-invalid={Boolean(tinyModelPromptError)}
                  aria-describedby={
                    tinyModelPromptError ? "tiny-model-prompt-error" : undefined
                  }
                  onChange={(event) => {
                    setSubjectPrompt(event.target.value);
                    invalidateGeneration();
                  }}
                />
                {tinyModelPromptError && (
                  <p
                    id="tiny-model-prompt-error"
                    className="text-xs text-destructive"
                    role="alert"
                  >
                    {tinyModelPromptError === "too_many_phrases"
                      ? t.promptTooMany
                      : t.promptTooLong}
                  </p>
                )}
              </div>
            )}
            <div className="space-y-2">
              <Label>{t.brand}</Label>
              <Select
                value={brand}
                onValueChange={(v) => {
                  setBrand(v as BrandId);
                  setHighlight(null);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {t.brandOption(BRANDS[brand].label, BRANDS[brand].colors.length)}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {(
                    Object.entries(BRANDS) as [
                      BrandId,
                      (typeof BRANDS)[BrandId],
                    ][]
                  ).map(([id, b]) => (
                    <SelectItem key={id} value={id}>
                      {t.brandOption(b.label, b.colors.length)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <Label htmlFor="beads">{t.widthBeads}</Label>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {beadsAcross}
                </span>
              </div>
              <Slider
                id="beads"
                min={10}
                max={MAX_BEADS}
                step={1}
                value={[beadsAcross]}
                disabled={controlsLocked}
                onValueChange={([v]) => {
                  setBeadsAcross(v!);
                  invalidateGeneration();
                }}
              />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <Label htmlFor="zoom">{t.zoom}</Label>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {cell}px
                </span>
              </div>
              <Slider
                id="zoom"
                min={5}
                max={28}
                step={1}
                value={[cell]}
                onValueChange={([v]) => setCell(v!)}
              />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <Label htmlFor="dither">{t.dithering}</Label>
              <Switch
                id="dither"
                checked={dither}
                onCheckedChange={setDither}
              />
            </div>
            {processingMode === "browser_native" && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="remove-background">{t.removeBackground}</Label>
                  <Switch
                    id="remove-background"
                    checked={removeBackground}
                    disabled={controlsLocked}
                    onCheckedChange={(checked) => {
                      setRemoveBackground(checked);
                      invalidateGeneration();
                    }}
                  />
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t.removeBackgroundDesc}
                </p>
              </div>
            )}
            <div className="flex items-center justify-between">
              <Label htmlFor="grid">{t.gridLines}</Label>
              <Switch
                id="grid"
                checked={grid}
                onCheckedChange={setGrid}
              />
            </div>
            <Separator />
            <Button
              className="w-full"
              disabled={
                !source ||
                generationState === "generating" ||
                (processingMode === "tiny_model" &&
                  (!tinyModelAvailable || Boolean(tinyModelPromptError)))
              }
              onClick={generationState === "ready" ? download : generate}
            >
              {generationState === "generating" ? (
                <>
                  <LoaderCircle className="animate-spin" />
                  {t.generating}
                </>
              ) : generationState === "ready" ? (
                <>
                  <Download />
                  {t.download}
                </>
              ) : (
                <>
                  <WandSparkles />
                  {t.generate}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {processingMode === "cv_native" && (
          <Card>
            <CardHeader>
              <CardTitle>{t.hyperparametersTitle}</CardTitle>
              <CardAction className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={controlsLocked || hyperparametersAreDefault}
                  onClick={resetHyperparameters}
                >
                  <RotateCcw />
                  {t.resetHyperparameters}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-expanded={hyperparametersExpanded}
                  aria-controls="cv-native-hyperparameters"
                  aria-label={
                    hyperparametersExpanded
                      ? t.collapseHyperparameters
                      : t.expandHyperparameters
                  }
                  onClick={() => setHyperparametersExpanded((expanded) => !expanded)}
                >
                  {hyperparametersExpanded ? <ChevronUp /> : <ChevronDown />}
                </Button>
              </CardAction>
            </CardHeader>
            {hyperparametersExpanded && (
              <CardContent id="cv-native-hyperparameters" className="space-y-5">
                {hyperparameterControls.map((control) => {
                  const value = hyperparameters[control.key];
                  return (
                    <div key={control.key} className="space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <Label htmlFor={`hp-${control.key}`} className="leading-5">
                          {control.label}
                        </Label>
                        <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                          {control.format ? control.format(value) : value}
                        </span>
                      </div>
                      <Slider
                        id={`hp-${control.key}`}
                        min={control.min}
                        max={control.max}
                        step={control.step}
                        value={[value]}
                        disabled={controlsLocked}
                        onValueChange={([next]) =>
                          updateHyperparameter(control.key, next!)
                        }
                      />
                    </div>
                  );
                })}
              </CardContent>
            )}
          </Card>
        )}
      </div>

      {/* ---- Pattern + legend ---- */}
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>{t.patternTitle}</CardTitle>
              {pattern && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">
                    {t.pegs(pattern.width, pattern.height)}
                  </Badge>
                  <Badge variant="secondary">
                    {t.beads(pattern.totalBeads.toLocaleString())}
                  </Badge>
                  <Badge variant="secondary">
                    {t.colorsUsed(pattern.used.length)}
                  </Badge>
                  {BRANDS[pattern.brand].pitchMm === 5 && (
                    <Badge variant="secondary">{t.pegboards(boards)}</Badge>
                  )}
                  <Badge variant="secondary">
                    {t.sizeCm(
                      ((pattern.width * BRANDS[pattern.brand].pitchMm) / 10).toFixed(1),
                      ((pattern.height * BRANDS[pattern.brand].pitchMm) / 10).toFixed(1)
                    )}
                  </Badge>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {pattern ? (
              <div className="max-h-[70vh] overflow-auto rounded-lg border bg-[#FAFAF8] p-2">
                <canvas ref={canvasRef} />
              </div>
            ) : (
              <div className="flex h-64 items-center justify-center text-muted-foreground">
                {t.emptyState}
              </div>
            )}
          </CardContent>
        </Card>

        {pattern && (
          <Card>
            <CardHeader>
              <CardTitle>{t.legendTitle}</CardTitle>
              <CardDescription>{t.legendDesc}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {pattern.used.map((u) => {
                  const c = BRANDS[pattern.brand].colors[u.index]!;
                  const active = highlight === u.index;
                  return (
                    <button
                      key={u.index}
                      type="button"
                      title={`${c.code} · ${c.hex}`}
                      onClick={() =>
                        setHighlight(active ? null : u.index)
                      }
                      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors ${
                        active
                          ? "border-primary bg-primary/10"
                          : "hover:bg-muted"
                      }`}
                    >
                      <span
                        className="inline-block size-4 rounded-full border border-black/20"
                        style={{ backgroundColor: c.hex }}
                      />
                      <span>{c.name}</span>
                      <span className="tabular-nums text-muted-foreground">
                        ×{u.count.toLocaleString()}
                      </span>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

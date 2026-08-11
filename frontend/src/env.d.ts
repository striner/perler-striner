/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_PROCESSOR_API_URL?: string;
  readonly PUBLIC_PROCESSOR_ALGORITHM?: string;
  readonly PUBLIC_PROCESSOR_ALGORITHM_VERSION?: string;
  readonly PUBLIC_PROCESSOR_ALGORITHM_PARAMS?: string;
  readonly PUBLIC_PROCESSOR_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

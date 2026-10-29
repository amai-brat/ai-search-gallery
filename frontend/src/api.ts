import type { ImageItem, IndexJob } from "./types";

// В dev-режиме /api проксируется Vite на FastAPI (см. vite.config.ts).
// Для сборки можно указать прямой адрес: VITE_API_URL=http://127.0.0.1:8000
const BASE: string = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("Не удаётся связаться с сервером", 0);
  }
  if (!res.ok) {
    let detail = `Ошибка ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* тело не JSON — оставляем общий текст */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export type Strictness = "strict" | "balanced" | "wide" | "off";

export interface SearchParams {
  semantic?: string;
  ocr?: string;
  limit?: number;
  strictness?: Strictness;
}

export const api = {
  listImages: (page: number, pageSize: number) =>
    request<{ results: ImageItem[]; total: number }>(
      `/images?page=${page}&pageSize=${pageSize}`,
    ),

  search: ({ semantic, ocr, limit = 20, strictness = "balanced" }: SearchParams) => {
    const q = new URLSearchParams({ limit: String(limit), strictness });
    if (semantic) q.set("semanticQuery", semantic);
    if (ocr) q.set("ocrQuery", ocr);
    return request<{ results: ImageItem[]; hidden_count: number }>(
      `/images/search?${q}`,
    );
  },

  jobs: () => request<{ results: IndexJob[] }>("/images/index/jobs"),

  indexFolder: (directoryPath: string) =>
    request<{ job_id: number }>("/images/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory_path: directoryPath }),
    }),

  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<{ job_id: number }>("/images/index/upload", {
      method: "POST",
      body: form,
    });
  },

  pickDirectory: () =>
    request<{ path: string | null }>("/fs/pick-directory", { method: "POST" }),

  fileUrl: (id: number) => `${BASE}/images/${id}/file`,
  thumbUrl: (id: number, size = 480) =>
    `${BASE}/images/${id}/thumbnail?size=${size}`,
};

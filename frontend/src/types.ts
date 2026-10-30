export type MatchKind = "semantic" | "ocr";

export interface ImageItem {
  id: number;
  filepath: string;
  sha256sum: string;
  added_at: string;
  ocr_text: string | null;
  /** Есть только у результатов поиска. */
  matched_by?: MatchKind[];
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface IndexJob {
  id: number;
  kind: "folder" | "upload";
  directory_path: string;
  status: JobStatus;
  total_files: number | null;
  processed_files: number;
  indexed_files: number;
  skipped_files: number;
  failed_files: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

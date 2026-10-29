import type { IndexJob } from "./types";

export function plural(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return forms[1];
  return forms[2];
}

export const files = (n: number) =>
  `${n.toLocaleString("ru-RU")} ${plural(n, ["файл", "файла", "файлов"])}`;

export const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

export function folderName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

const rtf = new Intl.RelativeTimeFormat("ru", { numeric: "auto" });

export function timeAgo(iso: string, now = Date.now()): string {
  const sec = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(sec);
  if (abs < 45) return "только что";
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  return rtf.format(Math.round(sec / 86400), "day");
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function duration(job: IndexJob): string | null {
  if (!job.started_at || !job.finished_at) return null;
  const sec = Math.max(
    0,
    Math.round(
      (new Date(job.finished_at).getTime() -
        new Date(job.started_at).getTime()) /
        1000,
    ),
  );
  if (sec < 60) return `${sec} с`;
  return `${Math.floor(sec / 60)} мин ${sec % 60} с`;
}

export const isActive = (job: IndexJob) =>
  job.status === "queued" || job.status === "running";

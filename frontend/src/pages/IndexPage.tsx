import {
  CircleAlert,
  CircleCheck,
  Clock,
  Folder,
  FolderOpen,
  ImagePlus,
  LoaderCircle,
  Plus,
  RefreshCw,
  Upload,
} from "lucide-react";
import { type DragEvent, useRef, useState } from "react";
import { api } from "../api";
import type { Toast } from "../App";
import { duration, files, folderName, isActive, timeAgo } from "../format";
import type { IndexJob } from "../types";

const IMAGE_RE = /\.(png|jpe?g|webp)$/i;

interface Props {
  jobs: IndexJob[];
  onChanged: () => void;
  notify: (kind: Toast["kind"], text: string) => void;
}

export function IndexPage({ jobs, onChanged, notify }: Props) {
  const [path, setPath] = useState("");
  const [picking, setPicking] = useState(false);
  const [queueing, setQueueing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const active = jobs.filter(isActive);
  const finished = jobs.filter((j) => !isActive(j));
  const stalled =
    active.length > 0 &&
    !active.some((j) => j.status === "running") &&
    Date.now() - new Date(active[active.length - 1].created_at).getTime() > 20_000;

  const queueFolder = async (dir: string) => {
    const value = dir.trim();
    if (!value) return;
    setQueueing(true);
    try {
      await api.indexFolder(value);
      notify("success", `«${folderName(value)}» поставлена в очередь`);
      setPath("");
      onChanged();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Не удалось поставить в очередь");
    } finally {
      setQueueing(false);
    }
  };

  const pickFolder = async () => {
    setPicking(true);
    try {
      const res = await api.pickDirectory();
      if (res.path) setPath(res.path);
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Не удалось открыть диалог");
    } finally {
      setPicking(false);
    }
  };

  const uploadFiles = async (list: File[]) => {
    const images = list.filter((f) => IMAGE_RE.test(f.name));
    if (images.length === 0) {
      notify("error", "Подходят только PNG, JPG и WEBP");
      return;
    }
    setUploading(true);
    try {
      await api.upload(images);
      notify("success", `${files(images.length)} загружено и поставлено в очередь`);
      onChanged();
    } catch (e) {
      notify("error", e instanceof Error ? e.message : "Не удалось загрузить");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void uploadFiles(Array.from(e.dataTransfer.files));
  };

  return (
    <div className="page">
      <section className="hero compact">
        <h1>Индексация</h1>
        <p>
          Добавьте папки или файлы: каждая картинка получит «смысловой» отпечаток и
          распознанный текст, после чего её можно искать.
        </p>
      </section>

      <div className="add-grid">
        <section className="panel">
          <h3>
            <FolderOpen size={18} /> Папка на компьютере
          </h3>
          <p className="panel-hint">
            Файлы останутся на месте, индексируются все PNG, JPG и WEBP, включая вложенные папки.
          </p>
          <div className="path-row">
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void queueFolder(path)}
              placeholder="C:\Users\...\Pictures"
              spellCheck={false}
              aria-label="Путь к папке"
            />
            <button className="btn ghost" onClick={pickFolder} disabled={picking}>
              {picking ? <LoaderCircle size={16} className="spin" /> : <Folder size={16} />}
              Обзор…
            </button>
          </div>
          <button
            className="btn primary full"
            onClick={() => queueFolder(path)}
            disabled={!path.trim() || queueing}
          >
            {queueing ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}
            Поставить в очередь
          </button>
        </section>

        <section
          className={dragging ? "panel drop dragging" : "panel drop"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInput.current?.click()}
        >
          <input
            ref={fileInput}
            type="file"
            accept=".png,.jpg,.jpeg,.webp"
            multiple
            hidden
            onChange={(e) => {
              void uploadFiles(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          <div className="drop-inner">
            <div className="empty-icon">
              {uploading ? <LoaderCircle size={26} className="spin" /> : <Upload size={26} />}
            </div>
            <h3>{uploading ? "Загружаем…" : "Загрузить картинки"}</h3>
            <p className="panel-hint">
              Перетащите файлы сюда или нажмите, чтобы выбрать. Копии сохранятся в хранилище приложения.
            </p>
          </div>
        </section>
      </div>

      <section className="block">
        <h2>
          Очередь
          {active.length > 0 && <span className="count">{active.length}</span>}
        </h2>
        {active.length === 0 ? (
          <div className="placeholder">
            <Clock size={16} /> Сейчас ничего не индексируется
          </div>
        ) : (
          <div className="jobs">
            {[...active].reverse().map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
        {stalled && (
          <div className="notice warn">
            Задача давно ждёт. Похоже, не запущен воркер Celery. Запустите{" "}
            <code>scripts\start.ps1</code>, и очередь продолжится.
          </div>
        )}
      </section>

      <section className="block">
        <h2>
          Проиндексировано
          {finished.length > 0 && <span className="count">{finished.length}</span>}
        </h2>
        {finished.length === 0 ? (
          <div className="placeholder">
            <ImagePlus size={16} /> Здесь появятся папки, которые уже в индексе
          </div>
        ) : (
          <div className="jobs">
            {finished.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                onRerun={
                  job.kind === "folder" ? () => void queueFolder(job.directory_path) : undefined
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function JobRow({ job, onRerun }: { job: IndexJob; onRerun?: () => void }) {
  const isUpload = job.kind === "upload";
  const title = isUpload ? "Загруженные файлы" : folderName(job.directory_path);
  const total = job.total_files;
  const pct = total ? Math.min(100, Math.round((job.processed_files / total) * 100)) : 0;
  const took = duration(job);

  return (
    <div className={`job ${job.status}`}>
      <div className="job-icon">
        {job.status === "running" && <LoaderCircle size={18} className="spin" />}
        {job.status === "queued" && <Clock size={18} />}
        {job.status === "done" && <CircleCheck size={18} />}
        {job.status === "failed" && <CircleAlert size={18} />}
      </div>

      <div className="job-main">
        <div className="job-title">
          <span className="job-name">{title}</span>
          <span className="job-time">{timeAgo(job.finished_at ?? job.created_at)}</span>
        </div>
        <div className="job-path" title={job.directory_path}>
          {isUpload ? "из браузера" : job.directory_path}
        </div>

        {job.status === "queued" && <div className="job-meta">Ждёт своей очереди…</div>}

        {job.status === "running" && (
          <>
            <div className={total ? "bar" : "bar indeterminate"}>
              <span style={{ width: `${pct}%` }} />
            </div>
            <div className="job-meta">
              {total === null
                ? "Считаем файлы…"
                : `${job.processed_files} из ${files(total)} · ${pct}%`}
              {job.failed_files > 0 && ` · ошибок: ${job.failed_files}`}
            </div>
          </>
        )}

        {job.status === "done" && (
          <div className="job-meta">
            {total === 0
              ? "Подходящих картинок в папке не нашлось"
              : [
                  `Новых: ${job.indexed_files}`,
                  job.skipped_files > 0 && `уже были: ${job.skipped_files}`,
                  job.failed_files > 0 && `ошибок: ${job.failed_files}`,
                  took && `за ${took}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
          </div>
        )}

        {job.status === "failed" && (
          <div className="job-meta danger">{job.error ?? "Не удалось проиндексировать"}</div>
        )}
      </div>

      {onRerun && (
        <button className="btn ghost small" onClick={onRerun} title="Проиндексировать заново и подхватить новые файлы">
          <RefreshCw size={14} /> Обновить
        </button>
      )}
    </div>
  );
}

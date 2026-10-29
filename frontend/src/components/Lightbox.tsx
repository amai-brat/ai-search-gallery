import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  ScanText,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect } from "react";
import { api } from "../api";
import { fileName, formatDate } from "../format";
import type { ImageItem } from "../types";

export function Lightbox({
  images,
  index,
  onChange,
  onClose,
}: {
  images: ImageItem[];
  index: number;
  onChange: (index: number) => void;
  onClose: () => void;
}) {
  const image = images[index];
  const hasPrev = index > 0;
  const hasNext = index < images.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && hasPrev) onChange(index - 1);
      if (e.key === "ArrowRight" && hasNext) onChange(index + 1);
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [index, hasPrev, hasNext, onChange, onClose]);

  if (!image) return null;
  const ocrText = image.ocr_text?.trim();

  return (
    <div className="lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <button className="lb-close icon-btn" onClick={onClose} aria-label="Закрыть">
        <X size={20} />
      </button>

      {hasPrev && (
        <button
          className="lb-nav prev"
          aria-label="Предыдущая"
          onClick={(e) => {
            e.stopPropagation();
            onChange(index - 1);
          }}
        >
          <ChevronLeft size={28} />
        </button>
      )}
      {hasNext && (
        <button
          className="lb-nav next"
          aria-label="Следующая"
          onClick={(e) => {
            e.stopPropagation();
            onChange(index + 1);
          }}
        >
          <ChevronRight size={28} />
        </button>
      )}

      <div className="lb-body" onClick={(e) => e.stopPropagation()}>
        <div className="lb-stage">
          <img key={image.id} src={api.fileUrl(image.id)} alt={fileName(image.filepath)} />
        </div>

        <aside className="lb-info">
          <h3>{fileName(image.filepath)}</h3>
          <p className="lb-path">{image.filepath}</p>

          {image.matched_by && (
            <div className="lb-row">
              {image.matched_by.includes("semantic") && (
                <span className="badge semantic">
                  <Sparkles size={11} /> найдено по смыслу
                </span>
              )}
              {image.matched_by.includes("ocr") && (
                <span className="badge ocr">
                  <ScanText size={11} /> найдено по тексту
                </span>
              )}
            </div>
          )}

          <dl>
            <dt>Добавлено в индекс</dt>
            <dd>{formatDate(image.added_at)}</dd>
          </dl>

          <div className="lb-ocr">
            <span className="label">Распознанный текст</span>
            {ocrText ? <p>{ocrText}</p> : <p className="muted">Текста на картинке не найдено</p>}
          </div>

          <a
            className="btn ghost"
            href={api.fileUrl(image.id)}
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink size={15} /> Открыть оригинал
          </a>
          <span className="lb-counter">
            {index + 1} / {images.length}
          </span>
        </aside>
      </div>
    </div>
  );
}

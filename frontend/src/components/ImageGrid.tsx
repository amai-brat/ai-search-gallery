import { ScanText, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { fileName } from "../format";
import type { ImageItem } from "../types";

function Card({
  image,
  index,
  onOpen,
}: {
  image: ImageItem;
  index: number;
  onOpen: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const name = fileName(image.filepath);

  return (
    <button
      className={loaded || failed ? "card loaded" : "card"}
      style={{ animationDelay: `${Math.min(index, 12) * 25}ms` }}
      onClick={onOpen}
      title={name}
    >
      {failed ? (
        <span className="card-missing">Файл недоступен</span>
      ) : (
        <img
          src={api.thumbUrl(image.id)}
          alt={name}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      )}

      {image.matched_by && (
        <span className="card-badges">
          {image.matched_by.includes("semantic") && (
            <span className="badge semantic">
              <Sparkles size={11} /> смысл
            </span>
          )}
          {image.matched_by.includes("ocr") && (
            <span className="badge ocr">
              <ScanText size={11} /> текст
            </span>
          )}
        </span>
      )}

      <span className="card-caption">{name}</span>
    </button>
  );
}

export function ImageGrid({
  images,
  onOpen,
}: {
  images: ImageItem[];
  onOpen: (index: number) => void;
}) {
  return (
    <div className="grid">
      {images.map((img, i) => (
        <Card key={img.id} image={img} index={i} onOpen={() => onOpen(i)} />
      ))}
    </div>
  );
}

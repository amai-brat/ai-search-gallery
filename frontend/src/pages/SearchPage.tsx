import {
  CircleHelp,
  ImagePlus,
  LoaderCircle,
  ScanText,
  Search,
  SearchX,
  Sparkles,
  X,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, type Strictness } from "../api";
import { ImageGrid } from "../components/ImageGrid";
import { Lightbox } from "../components/Lightbox";
import type { ImageItem } from "../types";

const PAGE_SIZE = 24;

const SEMANTIC_EXAMPLES = ["кошка", "дорожный знак", "горное озеро", "спортивная машина"];
const OCR_EXAMPLES = ["кофе", "яблоко", "apple"];

interface Query {
  semantic: string;
  ocr: string;
}

interface Settings {
  limit: number;
  strictness: Strictness;
}

const LIMITS = [10, 20, 40, 60, 100];
const STRICTNESS: { value: Strictness; label: string; hint: string }[] = [
  { value: "strict", label: "Строго", hint: "Только самые похожие" },
  { value: "balanced", label: "Баланс", hint: "Похожие без явного мусора" },
  { value: "wide", label: "Широко", hint: "Больше вариантов, возможны лишние" },
  { value: "off", label: "Всё", hint: "Без отсечения: ровно столько, сколько выбрано" },
];

function loadSettings(): Settings {
  const fallback: Settings = { limit: 20, strictness: "balanced" };
  try {
    const raw = JSON.parse(localStorage.getItem("searchSettings") ?? "null");
    if (
      raw &&
      LIMITS.includes(raw.limit) &&
      STRICTNESS.some((s) => s.value === raw.strictness)
    )
      return raw;
  } catch {
    /* нет доступа к хранилищу — берём значения по умолчанию */
  }
  return fallback;
}

export function SearchPage({
  total,
  onGoIndex,
}: {
  total: number | null;
  onGoIndex: () => void;
}) {
  const [semantic, setSemantic] = useState("");
  const [ocr, setOcr] = useState("");
  const [submitted, setSubmitted] = useState<Query | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [hidden, setHidden] = useState(0);

  const [results, setResults] = useState<ImageItem[]>([]);
  const [library, setLibrary] = useState<ImageItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<number | null>(null);
  const requestId = useRef(0);

  // --- поиск ---
  const runSearch = useCallback(async (q: Query, s: Settings) => {
    const id = ++requestId.current;
    setSubmitted(q);
    setLoading(true);
    setError(null);
    try {
      const res = await api.search({
        semantic: q.semantic || undefined,
        ocr: q.ocr || undefined,
        limit: s.limit,
        strictness: s.strictness,
      });
      if (id === requestId.current) {
        setResults(res.results);
        setHidden(res.hidden_count);
      }
    } catch (e) {
      if (id === requestId.current) {
        setResults([]);
        setHidden(0);
        setError(e instanceof Error ? e.message : "Что-то пошло не так");
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = { semantic: semantic.trim(), ocr: ocr.trim() };
    if (!q.semantic && !q.ocr) return reset();
    void runSearch(q, settings);
  };

  const changeSettings = (patch: Partial<Settings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      localStorage.setItem("searchSettings", JSON.stringify(next));
    } catch {
      /* не критично */
    }
    if (submitted) void runSearch(submitted, next);
  };

  const reset = () => {
    requestId.current++;
    setSemantic("");
    setOcr("");
    setSubmitted(null);
    setResults([]);
    setHidden(0);
    setError(null);
    setLoading(false);
  };

  const applyExample = (kind: keyof Query, value: string) => {
    const q = kind === "semantic" ? { semantic: value, ocr: "" } : { semantic: "", ocr: value };
    setSemantic(q.semantic);
    setOcr(q.ocr);
    void runSearch(q, settings);
  };

  // --- вся библиотека (когда запрос пуст) ---
  const loadLibrary = useCallback(async (count: number) => {
    try {
      const pages = Math.ceil(count / PAGE_SIZE);
      const all: ImageItem[] = [];
      for (let p = 1; p <= pages; p++) {
        const res = await api.listImages(p, PAGE_SIZE);
        all.push(...res.results);
        if (res.results.length < PAGE_SIZE) break;
      }
      setLibrary(all);
    } catch {
      /* ошибку связи показывает баннер в шапке */
    }
  }, []);

  const loadedCount = useRef(PAGE_SIZE);
  useEffect(() => {
    // total меняется, пока идёт индексация: подтягиваем новые картинки.
    void loadLibrary(loadedCount.current);
  }, [total, loadLibrary]);

  const loadMore = async () => {
    loadedCount.current += PAGE_SIZE;
    await loadLibrary(loadedCount.current);
  };

  const searching = submitted !== null;
  const shown = searching ? results : library;
  const libraryEmpty = total === 0;

  return (
    <div className="page">
      <section className="hero">
        <h1>Найдите картинку по смыслу или по тексту на ней</h1>
        <p>Опишите, что изображено, или введите слова, которые есть на картинке.</p>
      </section>

      <form className="searchbar" onSubmit={onSubmit}>
        <label className="field">
          <Sparkles size={18} className="field-icon semantic" />
          <input
            value={semantic}
            onChange={(e) => setSemantic(e.target.value)}
            placeholder="Что на картинке: «кошка на подоконнике»"
            aria-label="Поиск по смыслу"
          />
        </label>
        <span className="divider" />
        <label className="field">
          <ScanText size={18} className="field-icon ocr" />
          <input
            value={ocr}
            onChange={(e) => setOcr(e.target.value)}
            placeholder="Текст на картинке: «двуречье»"
            aria-label="Поиск по тексту на картинке"
          />
          <button
            type="button"
            className="help-btn"
            aria-label="Синтаксис запроса"
            onClick={() => setShowHelp((v) => !v)}
          >
            <CircleHelp size={16} />
          </button>
        </label>
        <button className="btn primary search-btn" type="submit">
          <Search size={16} /> Найти
        </button>
      </form>

      {showHelp && (
        <div className="help-pop">
          <b>Поиск по тексту понимает операторы:</b>
          <ul>
            <li><code>счёт оплата</code> — оба слова (AND)</li>
            <li><code>кофе OR чай</code> — любое из слов</li>
            <li><code>кофе NOT растворимый</code> — исключить слово</li>
            <li><code>"точная фраза"</code> — в кавычках, <code>кофе*</code> — любое окончание</li>
          </ul>
          Можно заполнить оба поля: результаты объединятся.
        </div>
      )}

      <div className="filters">
        <label className="filter">
          <span>Показывать до</span>
          <select
            value={settings.limit}
            onChange={(e) => changeSettings({ limit: Number(e.target.value) })}
            aria-label="Сколько картинок показывать"
          >
            {LIMITS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="filter">
          <span>Точность по смыслу</span>
          <div className="segmented" role="radiogroup" aria-label="Точность поиска по смыслу">
            {STRICTNESS.map((s) => (
              <button
                key={s.value}
                type="button"
                role="radio"
                aria-checked={settings.strictness === s.value}
                className={settings.strictness === s.value ? "seg active" : "seg"}
                title={s.hint}
                onClick={() => changeSettings({ strictness: s.value })}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!searching && !libraryEmpty && total !== null && (
        <div className="chips">
          <span className="chips-label">Попробуйте:</span>
          {SEMANTIC_EXAMPLES.map((ex) => (
            <button key={ex} className="chip semantic" onClick={() => applyExample("semantic", ex)}>
              <Sparkles size={12} /> {ex}
            </button>
          ))}
          {OCR_EXAMPLES.map((ex) => (
            <button key={ex} className="chip ocr" onClick={() => applyExample("ocr", ex)}>
              <ScanText size={12} /> {ex}
            </button>
          ))}
        </div>
      )}

      <div className="results-head">
        {searching ? (
          <>
            <h2>
              {loading ? "Ищем…" : `Найдено: ${results.length}`}
              {loading && <LoaderCircle size={16} className="spin" />}
            </h2>
            {!loading && hidden > 0 && (
              <span className="hidden-note">
                Скрыто менее похожих: {hidden}.{" "}
                <button
                  className="link"
                  onClick={() => changeSettings({ strictness: "off" })}
                >
                  Показать всё
                </button>
              </span>
            )}
            <button className="btn ghost small" onClick={reset}>
              <X size={14} /> Сбросить
            </button>
          </>
        ) : (
          !libraryEmpty && <h2>Вся библиотека</h2>
        )}
      </div>

      {error && (
        <div className="notice error">
          <b>Не получилось найти.</b> {error}
        </div>
      )}

      {libraryEmpty && !searching && (
        <div className="empty">
          <div className="empty-icon"><ImagePlus size={30} /></div>
          <h3>В индексе пока пусто</h3>
          <p>Добавьте папку с фотографиями или загрузите картинки, и здесь появится поиск.</p>
          <button className="btn primary" onClick={onGoIndex}>
            <ImagePlus size={16} /> Добавить картинки
          </button>
        </div>
      )}

      {searching && !loading && !error && results.length === 0 && (
        <div className="empty">
          <div className="empty-icon"><SearchX size={30} /></div>
          <h3>Ничего не нашлось</h3>
          <p>Попробуйте переформулировать запрос или поискать другими словами.</p>
        </div>
      )}

      {shown.length > 0 && (
        <div className={loading ? "dim" : undefined}>
          <ImageGrid images={shown} onOpen={setOpened} />
        </div>
      )}

      {!searching && total !== null && library.length < total && (
        <div className="more">
          <button className="btn ghost" onClick={loadMore}>
            Показать ещё ({total - library.length})
          </button>
        </div>
      )}

      {opened !== null && (
        <Lightbox
          images={shown}
          index={opened}
          onChange={setOpened}
          onClose={() => setOpened(null)}
        />
      )}
    </div>
  );
}

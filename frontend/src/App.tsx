import {
  CircleAlert,
  CircleCheck,
  Images,
  Layers,
  Moon,
  Search,
  Sun,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { isActive, plural } from "./format";
import { IndexPage } from "./pages/IndexPage";
import { SearchPage } from "./pages/SearchPage";
import type { IndexJob } from "./types";

type Tab = "search" | "index";
export interface Toast {
  id: number;
  kind: "success" | "error";
  text: string;
}

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (document.documentElement.dataset.theme as "light" | "dark") ?? "dark",
  );
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* приватный режим — не страшно */
    }
    setTheme(next);
  };
  return [theme, toggle] as const;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("search");
  const [theme, toggleTheme] = useTheme();
  const [jobs, setJobs] = useState<IndexJob[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [offline, setOffline] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [j, l] = await Promise.all([api.jobs(), api.listImages(1, 1)]);
      setJobs(j.results);
      setTotal(l.total);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  const hasActive = jobs.some(isActive);
  useEffect(() => {
    void refresh();
    // Пока что-то индексируется, опрашиваем чаще.
    const timer = setInterval(refresh, hasActive ? 1500 : 8000);
    return () => clearInterval(timer);
  }, [refresh, hasActive]);

  const activeCount = jobs.filter(isActive).length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark">
              <Search size={16} strokeWidth={2.6} />
            </span>
            <span className="brand-name">AI Search Gallery</span>
          </div>

          <nav className="tabs" aria-label="Разделы">
            <button
              className={tab === "search" ? "tab active" : "tab"}
              onClick={() => setTab("search")}
            >
              <Images size={16} /> Поиск
            </button>
            <button
              className={tab === "index" ? "tab active" : "tab"}
              onClick={() => setTab("index")}
            >
              <Layers size={16} /> Индексация
              {activeCount > 0 && <span className="tab-badge">{activeCount}</span>}
            </button>
          </nav>

          <div className="topbar-right">
            {total !== null && (
              <span className="counter" title="Картинок в индексе">
                {total.toLocaleString("ru-RU")}{" "}
                {plural(total, ["картинка", "картинки", "картинок"])}
              </span>
            )}
            <button
              className="icon-btn"
              onClick={toggleTheme}
              aria-label="Сменить тему"
              title="Сменить тему"
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </header>

      {offline && (
        <div className="banner">
          <CircleAlert size={16} />
          Нет связи с сервером. Проверьте, что API запущен
          (<code>scripts\start.ps1</code>) — страница подключится сама.
        </div>
      )}

      <main className="container">
        {tab === "search" ? (
          <SearchPage
            total={total}
            onGoIndex={() => setTab("index")}
          />
        ) : (
          <IndexPage jobs={jobs} onChanged={refresh} notify={notify} />
        )}
      </main>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === "success" ? <CircleCheck size={16} /> : <CircleAlert size={16} />}
            <span>{t.text}</span>
            <button
              className="toast-close"
              aria-label="Закрыть"
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

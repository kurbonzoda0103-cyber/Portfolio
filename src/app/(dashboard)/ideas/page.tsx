"use client";

import { useState } from "react";
import { Sparkles, Loader2, ChevronDown, ChevronUp, Copy, Check, Lightbulb } from "lucide-react";

interface Idea {
  title: string;
  hook: string;
  outline: string[];
  tags: string[];
  difficulty: "easy" | "medium" | "hard";
  estimatedViews: string;
  whyItWorks: string;
}

const FORMATS = [
  "Длинные видео (10-20 мин)",
  "Shorts (до 60 сек)",
  "Обучающие туториалы",
  "Влоги",
  "Обзоры и топы",
  "Интервью",
];

const difficultyLabel: Record<string, string> = { easy: "Лёгкое", medium: "Среднее", hard: "Сложное" };
const difficultyColor: Record<string, string> = {
  easy: "bg-green-500/15 text-green-400 border-green-500/20",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/20",
  hard: "bg-red-500/15 text-red-400 border-red-500/20",
};

function IdeaCard({ idea, index }: { idea: Idea; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const [copied, setCopied] = useState(false);

  function copyTitle() {
    navigator.clipboard.writeText(idea.title);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="glass rounded-xl overflow-hidden hover:border-white/15 transition-all">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-start gap-4 p-5 text-left"
      >
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center text-white font-bold text-sm shrink-0 mt-0.5">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold leading-snug">{idea.title}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className={`px-2 py-0.5 text-[10px] rounded border ${difficultyColor[idea.difficulty] || difficultyColor.medium}`}>
              {difficultyLabel[idea.difficulty] || idea.difficulty}
            </span>
            <span className="text-white/40 text-xs">~{idea.estimatedViews} просмотров</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); copyTitle(); }}
            className="p-1.5 rounded-lg hover:bg-white/10 text-white/40 hover:text-white transition-all"
          >
            {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
          </button>
          {open ? <ChevronUp size={16} className="text-white/40" /> : <ChevronDown size={16} className="text-white/40" />}
        </div>
      </button>

      {open && (
        <div className="px-5 pb-5 border-t border-white/8 pt-4 space-y-4">
          <div>
            <p className="text-white/40 text-[10px] uppercase tracking-wide mb-2">Хук (первые 30 сек)</p>
            <p className="text-white/80 text-sm leading-relaxed bg-white/4 rounded-xl p-3 border-l-2 border-red-500/50">
              {idea.hook}
            </p>
          </div>

          <div>
            <p className="text-white/40 text-[10px] uppercase tracking-wide mb-2">Структура видео</p>
            <ol className="space-y-1.5">
              {idea.outline.map((point, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-white/70">
                  <span className="w-5 h-5 rounded bg-white/8 flex items-center justify-center text-[10px] text-white/40 shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  {point}
                </li>
              ))}
            </ol>
          </div>

          <div>
            <p className="text-white/40 text-[10px] uppercase tracking-wide mb-2">Теги</p>
            <div className="flex flex-wrap gap-1.5">
              {idea.tags.map((tag) => (
                <span key={tag} className="px-2 py-0.5 bg-white/5 border border-white/10 rounded text-white/50 text-xs">
                  #{tag}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-amber-500/8 border border-amber-500/20 rounded-xl p-3 flex gap-2">
            <Lightbulb size={14} className="text-amber-400 shrink-0 mt-0.5" />
            <p className="text-amber-200/70 text-xs leading-relaxed">{idea.whyItWorks}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function IdeasPage() {
  const [niche, setNiche] = useState("");
  const [audience, setAudience] = useState("");
  const [format, setFormat] = useState(FORMATS[0]);
  const [language, setLanguage] = useState("ru");
  const [loading, setLoading] = useState(false);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState("");

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!niche.trim()) return;
    setLoading(true);
    setError("");
    setIdeas([]);
    try {
      const res = await fetch("/api/ideas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ niche, audience, format, language }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Ошибка");
      setIdeas(data.ideas || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
          <Sparkles className="text-amber-400" /> Генератор идей
        </h1>
        <p className="text-white/40">Claude AI генерирует идеи для видео с хуком, структурой и тегами</p>
      </div>

      <form onSubmit={handleGenerate} className="glass rounded-xl p-6 mb-8 space-y-4">
        <div>
          <label className="block text-white/60 text-xs uppercase tracking-wide mb-2">
            Твоя ниша / тема канала *
          </label>
          <input
            type="text"
            value={niche}
            onChange={(e) => setNiche(e.target.value)}
            placeholder="Например: личные финансы для студентов, веб-разработка на Python, путешествия соло..."
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/25 focus:outline-none focus:border-amber-500/50 transition-all"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-white/60 text-xs uppercase tracking-wide mb-2">
              Целевая аудитория
            </label>
            <input
              type="text"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="Например: студенты 18-25 лет..."
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-white/25 focus:outline-none focus:border-amber-500/50 transition-all"
            />
          </div>
          <div>
            <label className="block text-white/60 text-xs uppercase tracking-wide mb-2">
              Формат видео
            </label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-amber-500/50 transition-all"
            >
              {FORMATS.map((f) => (
                <option key={f} value={f} className="bg-gray-900">{f}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-white/60 text-xs uppercase tracking-wide mb-2">
            Язык контента
          </label>
          <div className="flex gap-2">
            {[{ v: "ru", label: "Русский" }, { v: "en", label: "English" }].map(({ v, label }) => (
              <button
                key={v}
                type="button"
                onClick={() => setLanguage(v)}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  language === v
                    ? "bg-amber-600 text-white"
                    : "bg-white/5 text-white/50 hover:text-white border border-white/10"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !niche.trim()}
          className="w-full py-3.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2"
        >
          {loading ? (
            <><Loader2 size={18} className="animate-spin" /> Claude думает...</>
          ) : (
            <><Sparkles size={18} /> Сгенерировать 8 идей</>
          )}
        </button>
      </form>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">
          {error}
        </div>
      )}

      {ideas.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-bold text-lg">
              {ideas.length} идей для &ldquo;{niche}&rdquo;
            </h2>
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="flex items-center gap-1.5 text-white/40 hover:text-white text-xs transition-colors"
            >
              <Sparkles size={12} /> Ещё идеи
            </button>
          </div>
          <div className="space-y-3">
            {ideas.map((idea, i) => (
              <IdeaCard key={i} idea={idea} index={i} />
            ))}
          </div>
        </>
      )}

      {!ideas.length && !loading && (
        <div className="text-center py-20">
          <div className="w-16 h-16 bg-amber-500/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Sparkles size={28} className="text-amber-400/50" />
          </div>
          <p className="text-white/30 text-sm">Опиши свою нишу и Claude придумает идеи</p>
          <div className="flex flex-wrap gap-2 justify-center mt-6">
            {["финансы для молодёжи", "фитнес дома", "Python для новичков", "путешествия"].map((tag) => (
              <button
                key={tag}
                onClick={() => setNiche(tag)}
                className="px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-white/50 hover:text-white text-xs transition-all"
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

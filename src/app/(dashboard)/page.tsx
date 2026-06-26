"use client";

import { useState } from "react";
import { Search, Loader2, TrendingUp, Users, DollarSign, Eye, ExternalLink } from "lucide-react";

interface Channel {
  id: string;
  title: string;
  subscribers: number;
  views: number;
  estimatedMonthlyRevenue: number;
  niche: string;
  thumbnailUrl?: string;
  outlierScore?: number;
  uploadsPerMonth?: number;
  qualityRating?: string;
  isFaceless?: boolean;
}

interface NicheResult {
  query: string;
  channels: Channel[];
  avgRpm: number;
  totalChannels: number;
}

function fmt(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
  return String(n);
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof TrendingUp;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="glass rounded-xl p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
        <Icon size={18} className="text-white" />
      </div>
      <div>
        <p className="text-white/40 text-xs">{label}</p>
        <p className="text-white font-bold text-lg">{value}</p>
      </div>
    </div>
  );
}

function ChannelCard({ ch }: { ch: Channel }) {
  return (
    <div className="glass rounded-xl p-5 hover:border-white/15 transition-all group">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center text-white font-bold text-sm">
            {ch.title.charAt(0)}
          </div>
          <div>
            <p className="text-white font-semibold text-sm leading-tight line-clamp-1">{ch.title}</p>
            <p className="text-white/40 text-xs mt-0.5">{ch.niche}</p>
          </div>
        </div>
        <a
          href={`https://youtube.com/channel/${ch.id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-0 group-hover:opacity-100 transition-opacity text-white/40 hover:text-white"
        >
          <ExternalLink size={14} />
        </a>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white/4 rounded-lg p-2.5">
          <p className="text-white/40 text-[10px] uppercase tracking-wide">Подписчики</p>
          <p className="text-white font-bold text-sm mt-0.5">{fmt(ch.subscribers)}</p>
        </div>
        <div className="bg-white/4 rounded-lg p-2.5">
          <p className="text-white/40 text-[10px] uppercase tracking-wide">Просмотры</p>
          <p className="text-white font-bold text-sm mt-0.5">{fmt(ch.views)}</p>
        </div>
        <div className="bg-white/4 rounded-lg p-2.5">
          <p className="text-white/40 text-[10px] uppercase tracking-wide">Доход/мес</p>
          <p className="text-green-400 font-bold text-sm mt-0.5">
            ${fmt(ch.estimatedMonthlyRevenue)}
          </p>
        </div>
        <div className="bg-white/4 rounded-lg p-2.5">
          <p className="text-white/40 text-[10px] uppercase tracking-wide">Outlier</p>
          <p className={`font-bold text-sm mt-0.5 ${
            (ch.outlierScore ?? 0) >= 2 ? "text-green-400" :
            (ch.outlierScore ?? 0) >= 1 ? "text-yellow-400" : "text-white/60"
          }`}>
            {ch.outlierScore?.toFixed(1) ?? "—"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3">
        {ch.isFaceless && (
          <span className="px-2 py-0.5 bg-purple-500/15 text-purple-400 text-[10px] rounded-full border border-purple-500/20">
            Faceless
          </span>
        )}
        {ch.qualityRating && (
          <span className={`px-2 py-0.5 text-[10px] rounded-full border ${
            ch.qualityRating === "high"
              ? "bg-green-500/15 text-green-400 border-green-500/20"
              : ch.qualityRating === "mid"
              ? "bg-yellow-500/15 text-yellow-400 border-yellow-500/20"
              : "bg-white/5 text-white/40 border-white/10"
          }`}>
            {ch.qualityRating === "high" ? "Высокое кач." : ch.qualityRating === "mid" ? "Среднее кач." : "Базовое"}
          </span>
        )}
        {ch.uploadsPerMonth && (
          <span className="px-2 py-0.5 bg-white/5 text-white/40 text-[10px] rounded-full border border-white/10">
            {ch.uploadsPerMonth} вид/мес
          </span>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NicheResult | null>(null);
  const [error, setError] = useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`/api/niche?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Ошибка");
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Что-то пошло не так");
    } finally {
      setLoading(false);
    }
  }

  const avgRevenue = result
    ? Math.round(result.channels.reduce((s, c) => s + c.estimatedMonthlyRevenue, 0) / (result.channels.length || 1))
    : 0;

  const totalSubs = result
    ? result.channels.reduce((s, c) => s + c.subscribers, 0)
    : 0;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-2">Поиск ниш</h1>
        <p className="text-white/40">Введи тему и найди прибыльные YouTube ниши с аналитикой</p>
      </div>

      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Например: финансы для молодёжи, кулинария, путешествия..."
              className="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-white/25 focus:outline-none focus:border-red-500/50 focus:bg-white/8 transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-6 py-3.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
            Найти
          </button>
        </div>
      </form>

      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="grid grid-cols-4 gap-4 mb-8">
            <StatCard icon={Users} label="Каналов найдено" value={String(result.channels.length)} color="bg-blue-600" />
            <StatCard icon={DollarSign} label="Средний доход/мес" value={`$${fmt(avgRevenue)}`} color="bg-green-600" />
            <StatCard icon={Eye} label="Всего подписчиков" value={fmt(totalSubs)} color="bg-purple-600" />
            <StatCard icon={TrendingUp} label="Средний RPM" value={`$${result.avgRpm.toFixed(2)}`} color="bg-orange-600" />
          </div>

          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-white font-bold text-lg">
              Каналы в нише &ldquo;{result.query}&rdquo;
            </h2>
            <p className="text-white/40 text-sm">{result.channels.length} результатов</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {result.channels.map((ch) => (
              <ChannelCard key={ch.id} ch={ch} />
            ))}
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="text-center py-24">
          <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Search size={28} className="text-white/20" />
          </div>
          <p className="text-white/30 text-sm">Введи тему чтобы найти каналы и ниши</p>
          <div className="flex flex-wrap gap-2 justify-center mt-6">
            {["финансы", "здоровье", "технологии", "кулинария", "путешествия", "бизнес"].map((tag) => (
              <button
                key={tag}
                onClick={() => setQuery(tag)}
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

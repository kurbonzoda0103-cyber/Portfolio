"use client";
import { useState } from "react";
import { Target, Search, Loader2, Users, Eye, DollarSign, TrendingUp, ExternalLink } from "lucide-react";

interface Competitor { id: string; title: string; subscribers: number; views: number; monthlyRevenue: number; uploadsPerMonth: number; avgViewsPerVideo: number; engagementRate: number; isFaceless: boolean; }
function fmt(n: number) { if(n>=1_000_000)return(n/1_000_000).toFixed(1)+"M"; if(n>=1_000)return(n/1_000).toFixed(0)+"K"; return String(n); }
function pct(n: number) { return (n*100).toFixed(2)+"%"; }

export default function CompetitorsPage() {
  const [channelUrl,setChannelUrl]=useState("");
  const [loading,setLoading]=useState(false);
  const [competitors,setCompetitors]=useState<Competitor[]>([]);
  const [error,setError]=useState("");
  const [anchor,setAnchor]=useState<Competitor|null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault(); if(!channelUrl.trim())return;
    setLoading(true);setError("");setCompetitors([]);setAnchor(null);
    try { const res=await fetch(`/api/competitors?channel=${encodeURIComponent(channelUrl)}`); const data=await res.json(); if(!res.ok)throw new Error(data.error||"Ошибка"); setAnchor(data.anchor||null);setCompetitors(data.competitors||[]); }
    catch(err:unknown){setError(err instanceof Error?err.message:"Ошибка");} finally{setLoading(false);}
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8"><h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3"><Target className="text-red-400"/>Анализ конкурентов</h1><p className="text-white/40">Введи URL канала и найди похожие каналы с метриками</p></div>
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30"/><input type="text" value={channelUrl} onChange={e=>setChannelUrl(e.target.value)} placeholder="https://youtube.com/@channel или ID канала..." className="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-white/25 focus:outline-none focus:border-red-500/50 transition-all"/></div>
          <button type="submit" disabled={loading||!channelUrl.trim()} className="px-6 py-3.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center gap-2">{loading?<Loader2 size={18} className="animate-spin"/>:<Search size={18}/>}Найти</button>
        </div>
      </form>
      {error&&<div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">{error}</div>}
      {anchor&&(
        <div className="mb-8 p-5 glass rounded-xl border border-blue-500/20">
          <p className="text-white/40 text-xs uppercase tracking-wide mb-3">Ваш канал</p>
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center text-white font-bold">{anchor.title.charAt(0)}</div>
            <div><p className="text-white font-bold">{anchor.title}</p><div className="flex items-center gap-4 mt-1 text-sm"><span className="text-white/50 flex items-center gap-1"><Users size={12}/>{fmt(anchor.subscribers)}</span><span className="text-white/50 flex items-center gap-1"><Eye size={12}/>{fmt(anchor.views)}</span><span className="text-green-400 flex items-center gap-1"><DollarSign size={12}/>${fmt(anchor.monthlyRevenue)}/мес</span></div></div>
          </div>
        </div>
      )}
      {competitors.length>0&&(
        <><h2 className="text-white font-bold text-lg mb-4">Похожие каналы ({competitors.length})</h2>
        <div className="space-y-3">{competitors.map((c,i)=>(
          <div key={c.id} className="glass rounded-xl p-5 hover:border-white/15 transition-all">
            <div className="flex items-center gap-4">
              <div className="w-8 text-white/30 font-bold text-sm shrink-0">{i+1}</div>
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center text-white font-bold text-sm shrink-0">{c.title.charAt(0)}</div>
              <div className="flex-1 min-w-0"><p className="text-white font-semibold text-sm">{c.title}</p></div>
              <div className="flex items-center gap-6 shrink-0">
                <div className="text-center"><p className="text-white/30 text-[10px]">Подписчики</p><p className="text-white font-bold text-sm">{fmt(c.subscribers)}</p></div>
                <div className="text-center"><p className="text-white/30 text-[10px]">Просм/видео</p><p className="text-white font-bold text-sm">{fmt(c.avgViewsPerVideo)}</p></div>
                <div className="text-center"><p className="text-white/30 text-[10px]">Вовлечённость</p><p className="text-yellow-400 font-bold text-sm">{pct(c.engagementRate)}</p></div>
                <div className="text-center"><p className="text-white/30 text-[10px]">Доход/мес</p><p className="text-green-400 font-bold text-sm">${fmt(c.monthlyRevenue)}</p></div>
                <a href={`https://youtube.com/channel/${c.id}`} target="_blank" rel="noopener noreferrer" className="text-white/30 hover:text-white transition-colors"><ExternalLink size={14}/></a>
              </div>
            </div>
          </div>
        ))}</div></>
      )}
      {!competitors.length&&!loading&&!anchor&&(
        <div className="text-center py-24"><div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4"><TrendingUp size={28} className="text-white/20"/></div><p className="text-white/30 text-sm">Введи URL канала для анализа конкурентов</p></div>
      )}
    </div>
  );
}

"use client";
import { useState } from "react";
import { Compass, Search, Loader2, TrendingUp, BarChart2 } from "lucide-react";

interface Keyword { keyword: string; searchVolume: number; competition: "low"|"medium"|"high"; cpc: number; trend: "up"|"stable"|"down"; relatedKeywords: string[]; }
function fmt(n: number) { if(n>=1_000_000)return(n/1_000_000).toFixed(1)+"M"; if(n>=1_000)return(n/1_000).toFixed(0)+"K"; return String(n); }
const compColor: Record<string,string>={low:"text-green-400 bg-green-500/10 border-green-500/20",medium:"text-yellow-400 bg-yellow-500/10 border-yellow-500/20",high:"text-red-400 bg-red-500/10 border-red-500/20"};
const compLabel: Record<string,string>={low:"Низкая",medium:"Средняя",high:"Высокая"};

export default function KeywordsPage() {
  const [query,setQuery]=useState("");
  const [loading,setLoading]=useState(false);
  const [keywords,setKeywords]=useState<Keyword[]>([]);
  const [error,setError]=useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault(); if(!query.trim())return;
    setLoading(true);setError("");setKeywords([]);
    try { const res=await fetch(`/api/keywords?q=${encodeURIComponent(query)}`); const data=await res.json(); if(!res.ok)throw new Error(data.error||"Ошибка"); setKeywords(data.keywords||[]); }
    catch(err:unknown){setError(err instanceof Error?err.message:"Ошибка");} finally{setLoading(false);}
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8"><h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3"><Compass className="text-red-400"/>Ключевые слова</h1><p className="text-white/40">Исследуй поисковый спрос и конкуренцию по ключевым словам</p></div>
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30"/><input type="text" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Введи ключевое слово..." className="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-white/25 focus:outline-none focus:border-red-500/50 transition-all"/></div>
          <button type="submit" disabled={loading||!query.trim()} className="px-6 py-3.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center gap-2">{loading?<Loader2 size={18} className="animate-spin"/>:<Search size={18}/>}Исследовать</button>
        </div>
      </form>
      {error&&<div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">{error}</div>}
      {keywords.length>0&&(
        <div className="space-y-3">{keywords.map(kw=>(
          <div key={kw.keyword} className="glass rounded-xl p-5">
            <div className="flex items-start justify-between mb-3"><p className="text-white font-semibold">{kw.keyword}</p><div className="flex items-center gap-2"><span className={`px-2 py-0.5 text-xs rounded border ${compColor[kw.competition]}`}>{compLabel[kw.competition]}</span><span className={`text-xs ${kw.trend==="up"?"text-green-400":kw.trend==="down"?"text-red-400":"text-white/40"}`}>{kw.trend==="up"?"↑ Растёт":kw.trend==="down"?"↓ Падает":"→ Стабильно"}</span></div></div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="bg-white/4 rounded-lg p-2.5"><p className="text-white/40 text-[10px] flex items-center gap-1"><BarChart2 size={10}/>Объём</p><p className="text-white font-bold text-sm mt-0.5">{fmt(kw.searchVolume)}/мес</p></div>
              <div className="bg-white/4 rounded-lg p-2.5"><p className="text-white/40 text-[10px] flex items-center gap-1"><TrendingUp size={10}/>CPC</p><p className="text-white font-bold text-sm mt-0.5">${kw.cpc.toFixed(2)}</p></div>
              <div className="bg-white/4 rounded-lg p-2.5"><p className="text-white/40 text-[10px]">Конкуренция</p><p className={`font-bold text-sm mt-0.5 ${kw.competition==="low"?"text-green-400":kw.competition==="medium"?"text-yellow-400":"text-red-400"}`}>{compLabel[kw.competition]}</p></div>
            </div>
            {kw.relatedKeywords.length>0&&(<div><p className="text-white/30 text-[10px] uppercase tracking-wide mb-2">Похожие</p><div className="flex flex-wrap gap-1.5">{kw.relatedKeywords.map(r=>(<button key={r} onClick={()=>setQuery(r)} className="px-2 py-0.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-white/50 hover:text-white text-xs transition-all">{r}</button>))}</div></div>)}
          </div>
        ))}</div>
      )}
      {!keywords.length&&!loading&&<div className="text-center py-24"><div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4"><Compass size={28} className="text-white/20"/></div><p className="text-white/30 text-sm">Введи ключевое слово для исследования</p></div>}
    </div>
  );
}

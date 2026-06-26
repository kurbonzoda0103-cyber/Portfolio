"use client";
import { useState, useEffect } from "react";
import { TrendingUp, Eye, ThumbsUp, Loader2, ExternalLink, RefreshCw } from "lucide-react";

interface TrendingVideo { id: string; title: string; channelTitle: string; viewCount: number; likeCount: number; thumbnailUrl: string; category: string; duration: string; }
function fmt(n: number) { if(n>=1_000_000)return(n/1_000_000).toFixed(1)+"M"; if(n>=1_000)return(n/1_000).toFixed(0)+"K"; return String(n); }
const CATS=[{id:"",label:"Все"},{id:"technology",label:"Технологии"},{id:"finance",label:"Финансы"},{id:"health",label:"Здоровье"},{id:"entertainment",label:"Развлечения"},{id:"education",label:"Образование"}];

export default function TrendingPage() {
  const [videos,setVideos]=useState<TrendingVideo[]>([]);
  const [loading,setLoading]=useState(true);
  const [category,setCategory]=useState("");
  const [error,setError]=useState("");

  async function load() {
    setLoading(true);setError("");
    try { const res=await fetch(`/api/trending?category=${encodeURIComponent(category)}`); const data=await res.json(); if(!res.ok)throw new Error(data.error||"Ошибка"); setVideos(data.videos||[]); }
    catch(err:unknown){setError(err instanceof Error?err.message:"Ошибка");} finally{setLoading(false);}
  }
  useEffect(()=>{load();},[category]); // eslint-disable-line

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div><h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3"><TrendingUp className="text-red-400"/>Тренды</h1><p className="text-white/40">Топ видео прямо сейчас на YouTube</p></div>
        <button onClick={load} disabled={loading} className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-white/60 hover:text-white text-sm transition-all"><RefreshCw size={14} className={loading?"animate-spin":""}/>Обновить</button>
      </div>
      <div className="flex gap-2 mb-8 overflow-x-auto scrollbar-hide">
        {CATS.map(c=><button key={c.id} onClick={()=>setCategory(c.id)} className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all ${category===c.id?"bg-red-600 text-white":"bg-white/5 text-white/50 hover:text-white hover:bg-white/10 border border-white/10"}`}>{c.label}</button>)}
      </div>
      {error&&<div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">{error}</div>}
      {loading?<div className="flex items-center justify-center py-32"><Loader2 size={28} className="animate-spin text-red-400"/></div>:(
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {videos.map(v=>(
            <a key={v.id} href={`https://youtube.com/watch?v=${v.id}`} target="_blank" rel="noopener noreferrer" className="glass rounded-xl overflow-hidden hover:border-white/15 transition-all group">
              {v.thumbnailUrl?<img src={v.thumbnailUrl} alt={v.title} className="w-full aspect-video object-cover"/>:<div className="w-full aspect-video bg-white/5 flex items-center justify-center"><TrendingUp size={24} className="text-white/20"/></div>}
              <div className="p-4">
                <p className="text-white font-semibold text-sm leading-tight line-clamp-2 mb-2 group-hover:text-red-300 transition-colors">{v.title}</p>
                <div className="flex items-center gap-1 text-white/40 text-xs mb-3"><span>{v.channelTitle}</span><ExternalLink size={10}/></div>
                <div className="flex items-center gap-4 text-white/50 text-xs"><span className="flex items-center gap-1"><Eye size={12}/>{fmt(v.viewCount)}</span><span className="flex items-center gap-1"><ThumbsUp size={12}/>{fmt(v.likeCount)}</span></div>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";
import { useState } from "react";
import { Video, Search, Loader2, Eye, ThumbsUp, MessageCircle, Clock, ExternalLink } from "lucide-react";

interface VideoAnalysis { id: string; title: string; channelTitle: string; description: string; viewCount: number; likeCount: number; commentCount: number; publishedAt: string; duration: string; thumbnailUrl: string; tags: string[]; transcript?: string; topComments: {text:string;likeCount:number}[]; }
function fmt(n: number) { if(n>=1_000_000)return(n/1_000_000).toFixed(1)+"M"; if(n>=1_000)return(n/1_000).toFixed(0)+"K"; return String(n); }

export default function VideosPage() {
  const [videoUrl,setVideoUrl]=useState("");
  const [loading,setLoading]=useState(false);
  const [video,setVideo]=useState<VideoAnalysis|null>(null);
  const [error,setError]=useState("");
  const [activeTab,setActiveTab]=useState<"overview"|"transcript"|"comments">("overview");

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault(); if(!videoUrl.trim())return;
    setLoading(true);setError("");setVideo(null);
    try { const res=await fetch(`/api/video?url=${encodeURIComponent(videoUrl)}`); const data=await res.json(); if(!res.ok)throw new Error(data.error||"Ошибка"); setVideo(data); }
    catch(err:unknown){setError(err instanceof Error?err.message:"Ошибка");} finally{setLoading(false);}
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8"><h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3"><Video className="text-red-400"/>Анализ видео</h1><p className="text-white/40">Введи ссылку на видео — получи статистику и топ комментарии</p></div>
      <form onSubmit={handleAnalyze} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30"/><input type="text" value={videoUrl} onChange={e=>setVideoUrl(e.target.value)} placeholder="https://youtube.com/watch?v=..." className="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-white/25 focus:outline-none focus:border-red-500/50 transition-all"/></div>
          <button type="submit" disabled={loading||!videoUrl.trim()} className="px-6 py-3.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center gap-2">{loading?<Loader2 size={18} className="animate-spin"/>:<Search size={18}/>}Анализ</button>
        </div>
      </form>
      {error&&<div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">{error}</div>}
      {video&&(
        <>
          <div className="glass rounded-xl overflow-hidden mb-6">
            <div className="flex gap-5 p-5">
              {video.thumbnailUrl&&<img src={video.thumbnailUrl} alt="" className="w-48 rounded-lg object-cover shrink-0"/>}
              <div className="flex-1 min-w-0">
                <h2 className="text-white font-bold text-lg leading-tight mb-2">{video.title}</h2>
                <div className="flex items-center gap-2 text-white/40 text-sm mb-4"><span>{video.channelTitle}</span><span>·</span><span>{new Date(video.publishedAt).toLocaleDateString("ru")}</span><span className="flex items-center gap-1"><Clock size={12}/>{video.duration}</span></div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-white/4 rounded-lg p-3"><div className="flex items-center gap-2 text-white/40 text-xs mb-1"><Eye size={12}/>Просмотры</div><p className="text-white font-bold">{fmt(video.viewCount)}</p></div>
                  <div className="bg-white/4 rounded-lg p-3"><div className="flex items-center gap-2 text-white/40 text-xs mb-1"><ThumbsUp size={12}/>Лайки</div><p className="text-white font-bold">{fmt(video.likeCount)}</p></div>
                  <div className="bg-white/4 rounded-lg p-3"><div className="flex items-center gap-2 text-white/40 text-xs mb-1"><MessageCircle size={12}/>Комментарии</div><p className="text-white font-bold">{fmt(video.commentCount)}</p></div>
                </div>
                <a href={`https://youtube.com/watch?v=${video.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 mt-3 text-red-400 hover:text-red-300 text-xs transition-colors"><ExternalLink size={12}/>Открыть на YouTube</a>
              </div>
            </div>
          </div>
          <div className="flex gap-2 mb-6">{(["overview","transcript","comments"] as const).map(tab=>(<button key={tab} onClick={()=>setActiveTab(tab)} className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${activeTab===tab?"bg-red-600 text-white":"bg-white/5 text-white/50 hover:text-white border border-white/10"}`}>{tab==="overview"?"Обзор":tab==="transcript"?"Транскрипт":"Комментарии"}</button>))}</div>
          {activeTab==="overview"&&video.description&&<div className="glass rounded-xl p-5"><p className="text-white/40 text-xs uppercase tracking-wide mb-3">Описание</p><p className="text-white/70 text-sm whitespace-pre-line leading-relaxed line-clamp-10">{video.description}</p></div>}
          {activeTab==="transcript"&&<div className="glass rounded-xl p-5"><p className="text-white/40 text-xs uppercase tracking-wide mb-3">Транскрипт</p>{video.transcript?<p className="text-white/70 text-sm leading-relaxed whitespace-pre-wrap">{video.transcript}</p>:<p className="text-white/30 text-sm">Транскрипт недоступен для этого видео</p>}</div>}
          {activeTab==="comments"&&<div className="space-y-3">{video.topComments.length===0?<p className="text-white/30 text-sm text-center py-8">Комментарии недоступны</p>:video.topComments.map((c,i)=>(<div key={i} className="glass rounded-xl p-4"><p className="text-white/70 text-sm leading-relaxed">{c.text}</p><div className="flex items-center gap-1 mt-2 text-white/30 text-xs"><ThumbsUp size={11}/>{fmt(c.likeCount)} лайков</div></div>))}</div>}
        </>
      )}
      {!video&&!loading&&<div className="text-center py-24"><div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4"><Video size={28} className="text-white/20"/></div><p className="text-white/30 text-sm">Вставь ссылку на YouTube видео для анализа</p></div>}
    </div>
  );
}

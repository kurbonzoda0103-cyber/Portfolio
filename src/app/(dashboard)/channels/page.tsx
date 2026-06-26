"use client";
import { useState } from "react";
import { BarChart2, Search, Loader2, Users, Eye, DollarSign, TrendingUp, Calendar, ExternalLink } from "lucide-react";

interface ChannelAnalytics { id: string; title: string; description: string; subscribers: number; totalViews: number; videoCount: number; monthlyRevenue: number; avgViewsPerVideo: number; uploadsPerMonth: number; subscriberGrowthRate: number; estimatedYearlyRevenue: number; topVideos: {id:string;title:string;views:number;publishedAt:string}[]; recentGrowth: number; isFaceless: boolean; niche: string; rpm: number; }
function fmt(n: number) { if(n>=1_000_000)return(n/1_000_000).toFixed(1)+"M"; if(n>=1_000)return(n/1_000).toFixed(0)+"K"; return String(n); }

export default function ChannelsPage() {
  const [channelUrl,setChannelUrl]=useState("");
  const [loading,setLoading]=useState(false);
  const [channel,setChannel]=useState<ChannelAnalytics|null>(null);
  const [error,setError]=useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault(); if(!channelUrl.trim())return;
    setLoading(true);setError("");setChannel(null);
    try { const res=await fetch(`/api/channel?url=${encodeURIComponent(channelUrl)}`); const data=await res.json(); if(!res.ok)throw new Error(data.error||"Ошибка"); setChannel(data); }
    catch(err:unknown){setError(err instanceof Error?err.message:"Ошибка");} finally{setLoading(false);}
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8"><h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3"><BarChart2 className="text-red-400"/>Аналитика канала</h1><p className="text-white/40">Глубокий анализ любого YouTube канала</p></div>
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30"/><input type="text" value={channelUrl} onChange={e=>setChannelUrl(e.target.value)} placeholder="https://youtube.com/@channelname или ID..." className="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-white/25 focus:outline-none focus:border-red-500/50 transition-all"/></div>
          <button type="submit" disabled={loading||!channelUrl.trim()} className="px-6 py-3.5 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all flex items-center gap-2">{loading?<Loader2 size={18} className="animate-spin"/>:<Search size={18}/>}Анализ</button>
        </div>
      </form>
      {error&&<div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm mb-6">{error}</div>}
      {channel&&(
        <>
          <div className="glass rounded-xl p-6 mb-6">
            <div className="flex items-start gap-4 mb-6">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center text-white font-bold text-2xl">{channel.title.charAt(0)}</div>
              <div className="flex-1"><div className="flex items-center gap-3"><h2 className="text-white font-bold text-xl">{channel.title}</h2><a href={`https://youtube.com/channel/${channel.id}`} target="_blank" rel="noopener noreferrer" className="text-white/30 hover:text-white transition-colors"><ExternalLink size={14}/></a></div><p className="text-white/50 text-sm mt-2 line-clamp-2">{channel.description}</p></div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[{icon:Users,label:"Подписчики",value:fmt(channel.subscribers),color:"bg-blue-600/20 text-blue-400"},{icon:Eye,label:"Всего просмотров",value:fmt(channel.totalViews),color:"bg-purple-600/20 text-purple-400"},{icon:DollarSign,label:"Доход/месяц",value:`$${fmt(channel.monthlyRevenue)}`,color:"bg-green-600/20 text-green-400"},{icon:TrendingUp,label:"RPM",value:`$${channel.rpm.toFixed(2)}`,color:"bg-orange-600/20 text-orange-400"}].map(({icon:Icon,label,value,color})=>(
                <div key={label} className="bg-white/4 rounded-xl p-4"><div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${color}`}><Icon size={14}/></div><p className="text-white/40 text-xs">{label}</p><p className="text-white font-bold text-lg mt-0.5">{value}</p></div>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="glass rounded-xl p-4"><p className="text-white/40 text-xs mb-1 flex items-center gap-1"><Calendar size={11}/>Видео/месяц</p><p className="text-white font-bold text-2xl">{channel.uploadsPerMonth}</p></div>
            <div className="glass rounded-xl p-4"><p className="text-white/40 text-xs mb-1">Просм/видео</p><p className="text-white font-bold text-2xl">{fmt(channel.avgViewsPerVideo)}</p></div>
            <div className="glass rounded-xl p-4"><p className="text-white/40 text-xs mb-1">Рост/мес</p><p className={`font-bold text-2xl ${channel.subscriberGrowthRate>0?"text-green-400":"text-red-400"}`}>{channel.subscriberGrowthRate>0?"+":""}{channel.subscriberGrowthRate.toFixed(1)}%</p></div>
          </div>
          {channel.topVideos.length>0&&(
            <div className="glass rounded-xl p-5"><p className="text-white font-bold mb-4">Топ видео</p>
            <div className="space-y-3">{channel.topVideos.map((v,i)=>(
              <a key={v.id} href={`https://youtube.com/watch?v=${v.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 p-3 bg-white/4 rounded-xl hover:bg-white/8 transition-all group">
                <span className="text-white/30 font-bold text-sm w-5">{i+1}</span>
                <div className="flex-1 min-w-0"><p className="text-white/80 text-sm line-clamp-1 group-hover:text-white transition-colors">{v.title}</p><p className="text-white/30 text-xs mt-0.5">{new Date(v.publishedAt).toLocaleDateString("ru")}</p></div>
                <div className="flex items-center gap-1 text-white/50 text-sm shrink-0"><Eye size={12}/>{fmt(v.views)}</div>
              </a>
            ))}</div></div>
          )}
        </>
      )}
      {!channel&&!loading&&<div className="text-center py-24"><div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4"><BarChart2 size={28} className="text-white/20"/></div><p className="text-white/30 text-sm">Введи URL канала для глубокого анализа</p></div>}
    </div>
  );
}

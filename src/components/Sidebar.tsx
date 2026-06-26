"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, TrendingUp, BarChart2, Video, Compass, Target, Play, Sparkles } from "lucide-react";
import { clsx } from "clsx";

const nav = [
  { href: "/", label: "Поиск ниш", icon: Search },
  { href: "/trending", label: "Тренды", icon: TrendingUp },
  { href: "/competitors", label: "Конкуренты", icon: Target },
  { href: "/channels", label: "Каналы", icon: BarChart2 },
  { href: "/videos", label: "Видео", icon: Video },
  { href: "/keywords", label: "Ключевые слова", icon: Compass },
  { href: "/ideas", label: "Генератор идей ✨", icon: Sparkles },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-60 shrink-0 flex flex-col border-r border-white/8 bg-black/20">
      <div className="px-5 py-6 flex items-center gap-3 border-b border-white/8">
        <div className="w-9 h-9 bg-red-600 rounded-xl flex items-center justify-center">
          <Play size={18} className="text-white fill-white" />
        </div>
        <div>
          <p className="font-bold text-white text-sm">NicheLab</p>
          <p className="text-[11px] text-white/40">YouTube Research</p>
        </div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={clsx(
            "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
            path === href ? "bg-red-600/20 text-red-400 border border-red-500/20" : "text-white/50 hover:text-white hover:bg-white/5"
          )}>
            <Icon size={16} />{label}
          </Link>
        ))}
      </nav>
      <div className="p-4 m-3 rounded-xl bg-gradient-to-br from-red-900/30 to-orange-900/20 border border-red-500/20">
        <p className="text-xs font-semibold text-white/80 mb-1">Powered by</p>
        <p className="text-xs text-white/40">YouTube API · Claude AI</p>
      </div>
    </aside>
  );
}

import { NextRequest, NextResponse } from "next/server";
const YT="https://www.googleapis.com/youtube/v3";
function extractChannelId(url:string):{type:"id"|"handle"|"username";value:string}{
  try{const u=new URL(url);const p=u.pathname;
    if(p.startsWith("/@"))return{type:"handle",value:p.slice(2)};
    if(p.startsWith("/channel/"))return{type:"id",value:p.split("/channel/")[1].split("/")[0]};
    if(p.startsWith("/user/"))return{type:"username",value:p.split("/user/")[1].split("/")[0]};
  }catch{}
  if(url.startsWith("@"))return{type:"handle",value:url.slice(1)};
  if(url.startsWith("UC"))return{type:"id",value:url};
  return{type:"handle",value:url};
}
const RPM: Record<string,number>={finance:15,business:12,health:10,technology:8,education:6,default:3};
function guessRpm(desc:string){const d=desc.toLowerCase();for(const[k,r]of Object.entries(RPM))if(d.includes(k))return r;return RPM.default;}
export async function GET(req:NextRequest){
  const url=req.nextUrl.searchParams.get("url");
  if(!url)return NextResponse.json({error:"url required"},{status:400});
  const key=process.env.YOUTUBE_API_KEY;
  if(!key)return NextResponse.json({error:"YOUTUBE_API_KEY не задан"},{status:500});
  try{
    const ref=extractChannelId(url);
    const pk=ref.type==="id"?"id":ref.type==="handle"?"forHandle":"forUsername";
    const cr=await fetch(`${YT}/channels?part=snippet,statistics&${pk}=${encodeURIComponent(ref.value)}&key=${key}`);
    if(!cr.ok)throw new Error(`YouTube API ${cr.status}`);
    const cd=await cr.json();
    const ch=cd.items?.[0];
    if(!ch)return NextResponse.json({error:"Канал не найден"},{status:404});
    const subs=parseInt(ch.statistics.subscriberCount||"0");
    const totalViews=parseInt(ch.statistics.viewCount||"0");
    const videoCount=parseInt(ch.statistics.videoCount||"0");
    const months=Math.max(1,(Date.now()-new Date(ch.snippet.publishedAt).getTime())/(1000*60*60*24*30));
    const rpm=guessRpm(ch.snippet.description||"");
    const monthlyRevenue=Math.round((totalViews/months/1000)*rpm);
    const tr=await fetch(`${YT}/search?part=snippet&channelId=${ch.id}&order=viewCount&type=video&maxResults=5&key=${key}`);
    const td=tr.ok?await tr.json():{items:[]};
    let topVideos: {id:string;title:string;views:number;publishedAt:string}[]=[];
    if(td.items?.length){const vids=td.items.map((i:{id:{videoId:string}})=>i.id.videoId).join(",");const vr=await fetch(`${YT}/videos?part=statistics,snippet&id=${vids}&key=${key}`);if(vr.ok){const vd=await vr.json();topVideos=(vd.items||[]).map((v:{id:string;snippet:{title:string;publishedAt:string};statistics:{viewCount?:string}})=>({id:v.id,title:v.snippet.title,views:parseInt(v.statistics.viewCount||"0"),publishedAt:v.snippet.publishedAt}));}}
    return NextResponse.json({id:ch.id,title:ch.snippet.title,description:ch.snippet.description||"",subscribers:subs,totalViews,videoCount,monthlyRevenue,avgViewsPerVideo:videoCount?Math.round(totalViews/videoCount):0,uploadsPerMonth:Math.round(videoCount/months),subscriberGrowthRate:0,estimatedYearlyRevenue:monthlyRevenue*12,topVideos,recentGrowth:0,isFaceless:false,niche:"",rpm});
  }catch(err:unknown){return NextResponse.json({error:err instanceof Error?err.message:"Error"},{status:500});}
}

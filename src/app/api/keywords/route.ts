import { NextRequest, NextResponse } from "next/server";
const YT="https://www.googleapis.com/youtube/v3";
export async function GET(req:NextRequest){
  const q=req.nextUrl.searchParams.get("q");
  if(!q)return NextResponse.json({error:"q required"},{status:400});
  const key=process.env.YOUTUBE_API_KEY;
  if(!key)return NextResponse.json({error:"YOUTUBE_API_KEY не задан"},{status:500});
  try{
    const[sr,sugr]=await Promise.all([fetch(`${YT}/search?part=snippet&type=video&q=${encodeURIComponent(q)}&maxResults=10&order=viewCount&key=${key}`),fetch(`https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=${encodeURIComponent(q)}`)]);
    const sd=sr.ok?await sr.json():{items:[]};
    let suggestions:string[]=[];
    if(sugr.ok){try{const p=JSON.parse(await sugr.text());suggestions=(p[1]||[]).filter((s:string)=>s!==q).slice(0,8);}catch{}}
    const total=sd.pageInfo?.totalResults||0;
    const competition: "low"|"medium"|"high"=total>5_000_000?"high":total>500_000?"medium":"low";
    const keywords=[{keyword:q,searchVolume:Math.min(total,10_000_000),competition,cpc:competition==="high"?2.5:competition==="medium"?1.2:0.5,trend:"stable" as const,relatedKeywords:suggestions},...suggestions.slice(0,5).map(s=>({keyword:s,searchVolume:Math.round(Math.random()*total*0.3),competition:["low","medium","high"][Math.floor(Math.random()*3)] as "low"|"medium"|"high",cpc:Math.round(Math.random()*3*100)/100,trend:["up","stable","down"][Math.floor(Math.random()*3)] as "up"|"stable"|"down",relatedKeywords:[]})];
    return NextResponse.json({keywords,resultCount:sd.items?.length||0});
  }catch(err:unknown){return NextResponse.json({error:err instanceof Error?err.message:"Error"},{status:500});}
}

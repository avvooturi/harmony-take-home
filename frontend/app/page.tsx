"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";

type Employee={id:string;name:string;role:string;department:string;permissions:string[]};
type Attention={id:string;run_id:string;priority:string;title:string;evidence:string[];recommendation:string;status:string};
type Approval={id:string;tool_name:string;arguments:Record<string,unknown>;reason:string;evidence:string[];status:string};
type Audit={id:string;event_type:string;details:Record<string,unknown>;created_at:string};
const tabs=["Attention","Approvals","Agent","Audit"] as const; type Tab=typeof tabs[number];

export default function Home(){
 const [employee,setEmployee]=useState("emp-pm"),[employees,setEmployees]=useState<Employee[]>([]),[tab,setTab]=useState<Tab>("Attention");
 const [attention,setAttention]=useState<Attention[]>([]),[approvals,setApprovals]=useState<Approval[]>([]),[audit,setAudit]=useState<Audit[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const [messages,setMessages]=useState<string[]>(["Ask me about purchasing risk. I can recommend actions, but I cannot execute them without the application approval gate."]);
 const load=useCallback(async()=>{setError("");try{const [es,at,ap,au]=await Promise.all([request<Employee[]>("/employees",employee),request<Attention[]>("/attention",employee),request<Approval[]>("/approvals",employee),request<Audit[]>("/audit",employee)]);setEmployees(es);setAttention(at);setApprovals(ap);setAudit(au)}catch(e){setError((e as Error).message)}},[employee]);
 useEffect(()=>{load()},[load]);
 async function analyze(){setBusy(true);try{await request("/proactive/run",employee,{method:"POST"});await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function decide(id:string,decision:string){setBusy(true);try{await request(`/approvals/${id}/decision`,employee,{method:"POST",body:JSON.stringify({decision})});await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function chat(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget),message=String(f.get("message"));if(!message)return;setMessages(x=>[...x,`You: ${message}`]);e.currentTarget.reset();try{const r=await request<{message:string}>("/agent/chat",employee,{method:"POST",body:JSON.stringify({message})});setMessages(x=>[...x,`Agent: ${r.message}`])}catch(err){setError((err as Error).message)}}
 const who=employees.find(e=>e.id===employee);
 return <div className="shell"><aside className="side"><div className="brand">Harmony <span>Agent</span></div><nav className="nav">{tabs.map(t=><button key={t} className={tab===t?"active":""} onClick={()=>setTab(t)}>{t}</button>)}</nav></aside><main className="main">
  <div className="top"><div><h1>{tab}</h1><div className="muted">{who?.role} · {who?.department}</div></div><select className="switcher" value={employee} onChange={e=>setEmployee(e.target.value)}>{employees.map(e=><option value={e.id} key={e.id}>{e.name} — {e.role}</option>)}</select></div>
  {error&&<div className="card error"><b>Access or request error:</b> {error}</div>}
  {tab==="Attention"&&<><div className="row" style={{marginBottom:16}}><button disabled={busy} onClick={analyze}>{busy?"Analyzing…":"Run proactive analysis"}</button><span className="muted">Deterministic detection first; agent reasoning only after a risk is found.</span></div>{attention.length===0?<div className="card muted">No attention items for this employee.</div>:attention.map(a=><div className="card" key={a.id}><div className="row"><span className="eyebrow">{a.priority} PRIORITY</span><span className={`pill ${a.status==="OPEN"?"pending":""}`}>{a.status}</span></div><h2>{a.title}</h2><div className="evidence"><b>Evidence</b><ul>{a.evidence.map(x=><li key={x}>{x}</li>)}</ul></div><p><b>Recommended action:</b> {a.recommendation}</p><button onClick={()=>setTab("Approvals")}>Review approval</button></div>)}</>}
  {tab==="Approvals"&&<>{approvals.length===0?<div className="card muted">No approval requests for this employee.</div>:approvals.map(a=><div className="card" key={a.id}><div className="row"><span className={`pill ${a.status==="PENDING"?"pending":""}`}>{a.status}</span><b>{a.tool_name}</b></div><p>{a.reason}</p><div className="grid"><div><h3>Exact change</h3><pre>{JSON.stringify(a.arguments,null,2)}</pre></div><div><h3>Evidence</h3><ul>{a.evidence.map(x=><li key={x}>{x}</li>)}</ul></div></div>{a.status==="PENDING"&&<div className="row"><button disabled={busy} onClick={()=>decide(a.id,"APPROVE")}>Approve</button><button disabled={busy} className="danger" onClick={()=>decide(a.id,"REJECT")}>Reject</button></div>}</div>)}</>}
  {tab==="Agent"&&<div className="card"><div className="chat">{messages.map((m,i)=><div className="message" key={i}>{m}</div>)}</div><form className="input" onSubmit={chat}><input name="message" placeholder="What needs my attention?"/><button>Send</button></form></div>}
  {tab==="Audit"&&<div className="card audit"><table><thead><tr><th>Time</th><th>Event</th><th>Details</th></tr></thead><tbody>{audit.map(a=><tr key={a.id}><td>{new Date(a.created_at).toLocaleString()}</td><td>{a.event_type}</td><td><pre>{JSON.stringify(a.details,null,2)}</pre></td></tr>)}</tbody></table>{audit.length===0&&<p className="muted">No visible audit events.</p>}</div>}
 </main></div>
}


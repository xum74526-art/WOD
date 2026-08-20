"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, UserPlus, UsersThree } from "@phosphor-icons/react";
import { acceptTeamInvitation, createTeam, inviteTeamMember, listTeams, type TeamSnapshot } from "@/lib/internal-api";
import { errorMessage } from "@/lib/commerce-ui";

export function TeamWorkspace() {
  const [snapshot, setSnapshot] = useState<TeamSnapshot>({ teams: [], received_invitations: [] }); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setSnapshot(await listTeams()); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function act(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); } }
  function addTeam() { const name = window.prompt("团队名称"); if (name?.trim()) void act(() => createTeam(name.trim())); }
  function invite(teamId: number) { const email = window.prompt("成员邮箱"); if (email?.trim()) void act(() => inviteTeamMember(teamId, email.trim(), "member")); }
  return <section className="workspace-page internal-workspace"><div className="workspace-page__head"><p>ACCOUNT / ORGANIZATION</p><h1>团队管理</h1><span>把协作成员组织到真实团队，并记录成员角色。</span></div>
    <div className="internal-toolbar"><strong>{snapshot.teams.length} 个团队</strong><button onClick={addTeam} disabled={busy}><Plus size={16}/>创建团队</button></div>{error && <div className="commerce-error">{error}</div>}
    {snapshot.received_invitations.length > 0 && <section className="invitation-strip"><h2>待接受邀请</h2>{snapshot.received_invitations.map((item) => <article key={item.id}><span><strong>{item.team_name}</strong><small>角色：{item.role}</small></span><button onClick={() => void act(() => acceptTeamInvitation(item.id))}>接受邀请</button></article>)}</section>}
    <div className="team-grid">{snapshot.teams.length === 0 ? <div className="internal-empty"><UsersThree size={30}/><strong>还没有团队</strong><span>创建团队后可按邮箱邀请已注册成员。</span></div> : snapshot.teams.map((team) => <article className="team-card" key={team.id}><header><div><small>TEAM #{team.id}</small><h2>{team.name}</h2></div><button onClick={() => invite(team.id)}><UserPlus size={16}/>邀请</button></header><ul>{team.members.map((member) => <li key={member.user_id}><span>{member.display_name.slice(0, 1)}</span><div><strong>{member.display_name}</strong><small>{member.email || "未绑定邮箱"}</small></div><b>{member.role}</b></li>)}</ul></article>)}</div>
  </section>;
}

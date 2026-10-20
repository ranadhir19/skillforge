import { useCallback, useEffect, useState } from "react";
import { EVALS_QUERY, RUN_MUTATION, SKILLS_QUERY, gql, rest } from "./api";

const LIFECYCLE_COLORS = {
  active: "#1a7f37", shadow: "#9a6700", draft: "#57606a",
  imported: "#0550ae", deprecated: "#cf222e",
};

function Badge({ text }) {
  return (
    <span className="badge" style={{ background: LIFECYCLE_COLORS[text] || "#57606a" }}>
      {text}
    </span>
  );
}

function Library({ skills, selected, onSelect }) {
  return (
    <div className="library">
      <div className="cards">
        {skills.map((s) => (
          <button key={s.name} className={"card" + (selected?.name === s.name ? " sel" : "")}
                  onClick={() => onSelect(s)}>
            <div className="card-head"><strong>{s.name}</strong><Badge text={s.lifecycle} /></div>
            <p>{s.description}</p>
            <small>v{s.version} · tools: {s.tools.length} · scripts: {s.scripts.length}</small>
          </button>
        ))}
      </div>
      {selected && <SkillDetail skill={selected} />}
    </div>
  );
}

function SkillDetail({ skill }) {
  const [evals, setEvals] = useState(null);
  const [busy, setBusy] = useState(false);
  const runEvals = async () => {
    setBusy(true);
    try {
      const data = await gql(EVALS_QUERY, { name: skill.name });
      setEvals(data.skillEvals);
    } finally { setBusy(false); }
  };
  const rows = [
    ["Tools granted", skill.tools.join(", ") || "none"],
    ["Scripts it may run", skill.scripts.join(", ") || "none"],
    ["Network", skill.network],
    ["May write", skill.fsWrite.join(", ") || "sandbox only"],
    ["Needs approval for", skill.approvalRequiredFor.join(", ") || "nothing"],
    ["Governs actions", skill.governs.join(", ") || "—"],
    ["Output sections", skill.sections.join(" · ") || "—"],
    ["Composes", skill.composes.join(", ") || "—"],
    ["Conflicts", skill.conflicts.join(", ") || "—"],
    ["Provenance", `${skill.author} · ${skill.origin} · hash ${skill.contentHash}`],
  ];
  return (
    <div className="detail">
      <h3>{skill.name} <Badge text={skill.lifecycle} /></h3>
      <table>{rows.map(([k, v]) => (
        <tr key={k}><th>{k}</th><td>{v}</td></tr>))}</table>
      <h4>Should fire for</h4>
      <ul>{skill.triggerExamples.map((t) => <li key={t}>{t}</li>)}</ul>
      <h4>Should NOT fire for (near-misses)</h4>
      <ul>{skill.triggerCounterExamples.map((t) => <li key={t}>{t}</li>)}</ul>
      <button onClick={runEvals} disabled={busy}>
        {busy ? "Running eval suite…" : "Run this skill's eval suite"}
      </button>
      {evals && (
        <p className="eval-result">
          Eval suite on {evals.provider}: <strong>{evals.passed}/{evals.total}</strong>
          {" "}passed ({Math.round(evals.passRate * 100)}%)
        </p>
      )}
    </div>
  );
}

function Run({ skills }) {
  const [task, setTask] = useState(
    "Analyse Q1 2026 revenue: total revenue, the North region total, total costs, units sold, and net revenue, then write up the findings.");
  const [provider, setProvider] = useState("stub-pro");
  const [pin, setPin] = useState("");
  const [autoApprove, setAutoApprove] = useState(true);
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const data = await gql(RUN_MUTATION, {
        task, provider, autoApprove, pin: pin || null });
      setRun(data.triggerRun);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="run">
      <label>Task</label>
      <textarea rows={3} value={task} onChange={(e) => setTask(e.target.value)} />
      <div className="row">
        <label>Provider{" "}
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="stub-pro">stub-pro (offline, full capability)</option>
            <option value="stub-basic">stub-basic (offline, reduced precision)</option>
          </select>
        </label>
        <label>Pin skill{" "}
          <select value={pin} onChange={(e) => setPin(e.target.value)}>
            <option value="">(resolver decides)</option>
            {skills.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={autoApprove}
                 onChange={(e) => setAutoApprove(e.target.checked)} />
          {" "}Auto-approve gated steps (uncheck to watch the publish gate deny)
        </label>
        <button onClick={submit} disabled={busy}>{busy ? "Running…" : "Run task"}</button>
      </div>
      {error && <p className="error">{error}</p>}
      {run && (
        <div className="run-result">
          <p>
            <strong>Status:</strong> {run.status} · <strong>Primary skill:</strong>{" "}
            {run.primarySkill || "—"} · <strong>Tokens:</strong> {run.totalTokens} ·{" "}
            <strong>Cost:</strong> ${run.totalCostUsd.toFixed(4)} ·{" "}
            <strong>Plan:</strong> {run.planHash}
          </p>
          <table>
            <thead><tr><th>Step</th><th>Action</th><th>Governing skill</th>
              <th>Provider</th><th>Status</th><th>Tokens</th></tr></thead>
            <tbody>
              {run.traces.map((t) => (
                <tr key={t.stepId}>
                  <td>{t.stepId}</td><td>{t.action}</td><td>{t.skill || "—"}</td>
                  <td>{t.provider}</td>
                  <td className={"st-" + t.status}>{t.status}</td><td>{t.tokens}</td>
                </tr>))}
            </tbody>
          </table>
          <details>
            <summary>Resolver decisions</summary>
            <pre>{run.resolutionLog.join("\n")}</pre>
          </details>
          <h4>Deliverable</h4>
          <pre className="output">{run.finalOutput}</pre>
        </div>
      )}
    </div>
  );
}

function Create({ onCreated }) {
  const [description, setDescription] = useState(
    "Compute a margin watch for a quarter: total revenue, total costs, and the margin ratio, with the totals shown.");
  const [draft, setDraft] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const makeDraft = async () => {
    setBusy(true); setMessage("");
    try {
      const body = await rest("/skills/draft", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description }) });
      setDraft(body);
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  };

  const decide = async (approve) => {
    setBusy(true);
    try {
      const body = await rest(`/skills/${draft.draft_id}/decide`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approve, lifecycle: "shadow" }) });
      setMessage(approve
        ? `Registered "${body.skill}" as ${body.lifecycle}. It will be seen and logged by the resolver, but will not govern until promoted.`
        : `Draft "${body.skill}" denied at the gate — nothing was registered.`);
      setDraft(null);
      if (approve && onCreated) onCreated();
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="create">
      <p>Describe a capability. The platform drafts the package, validates it
         statically, trials it against its own starter evals in a sandbox —
         and then stops. Registration needs your approval, here.</p>
      <label>Capability description</label>
      <textarea rows={3} value={description}
                onChange={(e) => setDescription(e.target.value)} />
      <button onClick={makeDraft} disabled={busy}>
        {busy ? "Drafting + trialling…" : "Draft and trial a new skill"}
      </button>
      {draft && (
        <div className="draft">
          <h4>Draft: {draft.skill}</h4>
          <h5>What it asks for (the permission summary you are approving)</h5>
          <ul>{draft.permissions.map((l) => <li key={l}>{l}</li>)}</ul>
          <p>Trial: <strong>{draft.trial.passed}/{draft.trial.total}</strong> eval
             cases passed in the sandbox.</p>
          <div className="row">
            <button onClick={() => decide(true)} disabled={busy}>
              Approve — register as shadow</button>
            <button onClick={() => decide(false)} disabled={busy}>Deny</button>
          </div>
        </div>
      )}
      {message && <p className="message">{message}</p>}
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("library");
  const [skills, setSkills] = useState([]);
  const [selected, setSelected] = useState(null);
  const [health, setHealth] = useState(null);

  const reload = useCallback(async () => {
    const data = await gql(SKILLS_QUERY);
    setSkills(data.skills);
    setSelected((cur) => data.skills.find((s) => s.name === cur?.name) || data.skills[0]);
  }, []);

  useEffect(() => {
    reload().catch(() => {});
    rest("/health").then(setHealth).catch(() => {});
  }, [reload]);

  return (
    <div className="app">
      <header>
        <h1>SkillForge</h1>
        <p>Model-agnostic skills: portable packages, enforced permissions,
           evals before trust, humans at the gate.
           {health && <> · API: {health.status} · {health.skills} skills ·
             audit chain {health.audit_chain_valid ? "valid" : "BROKEN"}</>}</p>
        <nav>
          {["library", "run", "create"].map((t) => (
            <button key={t} className={tab === t ? "on" : ""}
                    onClick={() => setTab(t)}>{t}</button>))}
        </nav>
      </header>
      {tab === "library" && <Library skills={skills} selected={selected} onSelect={setSelected} />}
      {tab === "run" && <Run skills={skills} />}
      {tab === "create" && <Create onCreated={reload} />}
    </div>
  );
}

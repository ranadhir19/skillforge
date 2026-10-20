// SkillForge API client. GraphQL is the query layer (library,
// provenance, traces); REST carries runs-by-id, import/export and the
// staged creation gate. Base URL: VITE_API_URL at build time, else
// same-origin (the dev proxy forwards to the API service).
const BASE = import.meta.env.VITE_API_URL || "";

export async function gql(query, variables = {}) {
  const resp = await fetch(`${BASE}/graphql`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  const body = await resp.json();
  if (body.errors) throw new Error(body.errors.map((e) => e.message).join("; "));
  return body.data;
}

export async function rest(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, options);
  if (!resp.ok) throw new Error(`${path}: ${resp.status} ${await resp.text()}`);
  return resp.json();
}

export const SKILLS_QUERY = `{
  skills {
    name version lifecycle description tools scripts network fsWrite
    approvalRequiredFor composes conflicts governs sections
    triggerExamples triggerCounterExamples author origin contentHash
  }
}`;

export const EVALS_QUERY = `query($name: String!) {
  skillEvals(name: $name) { total passed passRate provider }
}`;

export const RUN_MUTATION = `mutation($task: String!, $provider: String!,
    $autoApprove: Boolean!, $pin: String) {
  triggerRun(task: $task, provider: $provider, autoApprove: $autoApprove,
             pinSkill: $pin) {
    status primarySkill activeSkills totalTokens totalCostUsd planHash
    finalOutput resolutionLog
    traces { stepId action skill provider status tokens detail }
  }
}`;

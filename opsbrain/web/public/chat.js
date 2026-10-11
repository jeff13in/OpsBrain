// Fixed synthetic examples; this module never sends a question to a service.
export const CHAT_SCENARIOS = Object.freeze([
  { id: 'ok', label: 'Successful investigation' },
  { id: 'partial', label: 'Code agent unavailable' },
  { id: 'error', label: 'All agents unavailable' },
]);

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

const results = [
  { agent: 'rag', status: 'ok', answer: 'The example runbook recommends checking CPU saturation and pod readiness before changing capacity. [1]', sources: ['Example runbook: service latency'], error: null },
  { agent: 'monitoring', status: 'ok', answer: 'The synthetic snapshot shows CPU at 68% and one warning alert. [2]', sources: ['Example monitoring snapshot'], error: null },
  { agent: 'infra', status: 'ok', answer: 'Two of three example pods are ready; inspect the unready pod before inferring capacity. [3]', sources: ['Example pod readiness snapshot'], error: null },
  { agent: 'code', status: 'ok', answer: 'An example deployment changed connection pooling. Timing alone does not establish a cause. [4]', sources: ['Example deployment change'], error: null },
];

export const CHAT_FIXTURES = freeze(Object.fromEntries(CHAT_SCENARIOS.map(({ id }) => {
  const agentResults = results.map(result => id === 'error' || (id === 'partial' && result.agent === 'code')
    ? { agent: result.agent, status: 'error', answer: '', sources: [], error: { code: 'unavailable', message: 'Synthetic dependency unavailable' } }
    : { ...result });
  return [id, {
    status: id,
    answer: id === 'error'
      ? 'No example agent returned context. No diagnosis is available.'
      : `In this fixed example, investigate CPU saturation [2] and the unready pod [3], using the latency runbook [1]. ${id === 'partial' ? 'Code context is unavailable, so deployment correlation cannot be assessed.' : 'The deployment change [4] is a lead to review, not a confirmed cause.'}`,
    sources: agentResults.flatMap(result => result.sources),
    results: agentResults,
  }];
})));

export function validateQuestion(value) {
  if (typeof value !== 'string') return 'Enter a question.';
  if (value.trim().length < 5) return 'Write at least five characters.';
  if (value.trim().length > 2000) return 'Keep your question within 2000 characters.';
  return '';
}

export async function demoReply(scenario) {
  if (!Object.hasOwn(CHAT_FIXTURES, scenario)) throw new Error('Unknown demo scenario');
  // A short local delay lets the loading state be inspected. No network work.
  await new Promise(resolve => setTimeout(resolve, 350));
  return CHAT_FIXTURES[scenario];
}

export function createChat({ reply = demoReply, onChange = () => {} } = {}) {
  let mode = 'demo';
  const initial = () => ({ turns: [], pending: false, validation: '', draft: '', scenario: 'ok', mode });
  let state = initial();
  let generation = 0;
  const notify = () => onChange();
  return {
    snapshot: () => freeze(structuredClone(state)),
    setMode(value) { mode = value === 'live' ? 'live' : 'demo'; this.clear(); },
    clear() {
      generation += 1;
      state = initial();
      notify();
    },
    restore(turns) {
      generation += 1;
      mode = 'demo'; state = { ...initial(), turns: structuredClone(turns) };
      notify();
    },
    async submit(question, scenario = 'ok') {
      if (state.pending) return false;
      state.validation = validateQuestion(question);
      state.draft = typeof question === 'string' ? question : '';
      if (mode === 'demo' && !Object.hasOwn(CHAT_FIXTURES, scenario)) state.validation = 'Choose a supported demo scenario.';
      if (state.validation) { notify(); return false; }
      if (state.turns.length >= 20) {
        state.validation = 'This preview holds 20 questions. Clear the demo conversation to continue.';
        notify(); return false;
      }
      state.scenario = scenario;
      const turn = { question: question.trim(), response: null, mode };
      state.turns.push(turn);
      state.draft = '';
      state.pending = true;
      const requestGeneration = generation;
      notify();
      try {
        const response = await reply(scenario, turn.question);
        if (generation !== requestGeneration) return false;
        turn.response = response;
      } catch {
        if (generation !== requestGeneration) return false;
        turn.response = { status: 'error', answer: mode === 'live' ? 'Live request failed or returned an invalid response. No demo fallback was used. Check the connection and try again.' : 'The demo response could not be prepared. Choose a scenario and try again.', sources: [], results: [] };
      }
      state.pending = false;
      notify();
      return true;
    },
  };
}

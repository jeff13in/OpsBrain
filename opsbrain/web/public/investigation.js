// Local report generation: only displayed fields, no network calls or persistence.
const text = (value, max) => typeof value === 'string' && value.length <= max;
const sources = value => Array.isArray(value) && value.length <= 20 && value.every(item => text(item, 2000));
const agents = ['rag', 'monitoring', 'infra', 'code'];
function validResponse(value) {
  return value && ['ok', 'partial', 'error'].includes(value.status) && text(value.answer, 20000) && sources(value.sources) &&
    Array.isArray(value.results) && value.results.length <= 4 && value.results.every(result =>
      agents.includes(result?.agent) && ['ok', 'error', 'timeout'].includes(result.status) &&
      (result.answer == null || text(result.answer, 20000)) && sources(result.sources) &&
      (result.latency_ms === undefined || Number.isInteger(result.latency_ms) && result.latency_ms >= 0 && result.latency_ms <= 3600000) &&
      (result.error == null || text(result.error.code, 100) && text(result.error.message, 2000))) &&
    (value.routing === undefined || value.routing && ['llm', 'keyword', 'fallback'].includes(value.routing.method) &&
      text(value.routing.reason, 2000) && Array.isArray(value.routing.agents) && value.routing.agents.length <= 4 && value.routing.agents.every(agent => agents.includes(agent)));
}

export function canExportInvestigation(state) {
  return !!state && !state.pending && Array.isArray(state.turns) && state.turns.length > 0 && state.turns.length <= 20 &&
    state.turns.every(turn => text(turn?.question, 2000) && turn.question.trim().length >= 5 &&
      ['demo', 'live'].includes(turn.mode || state.mode || 'demo') && validResponse(turn.response));
}

// Variable-length code fences keep HTML, links and embedded fences as literal text.
function literal(value) {
  const body = String(value).replace(/\r\n?/g, '\n');
  const fence = '`'.repeat(Math.max(3, ...[...body.matchAll(/`+/g)].map(match => match[0].length + 1)));
  return `${fence}text\n${body}\n${fence}\n`;
}

export function investigationReport(state) {
  if (!canExportInvestigation(state)) throw new Error('Complete the conversation before exporting.');
  const modes = [...new Set(state.turns.map(turn => turn.mode || state.mode || 'demo'))];
  const provenance = modes.length === 1 ? modes[0] === 'live' ? 'Live' : 'Demo' : 'Mixed';
  const sections = ['# OpsBrain investigation', `Provenance: ${provenance}.`, 'This report contains displayed conversation content. Demo results are synthetic. Live results are API responses, not independent verification. Downloading does not change saved history or retention.'];
  state.turns.forEach((turn, index) => {
    const response = turn.response;
    sections.push(`## Question ${index + 1}`, `Mode: ${(turn.mode || state.mode || 'demo') === 'live' ? 'Live' : 'Demo'}. Outcome: ${response.status}.`, literal(turn.question), '### Answer', literal(response.answer), '### Sources');
    response.sources.forEach((source, i) => sections.push(`Source [${i + 1}]`, literal(source)));
    if (!response.sources.length) sections.push('No sources available.');
    if (response.routing) sections.push('### Routing', `Method: ${response.routing.method}. Agents: ${response.routing.agents.join(', ')}.`, literal(response.routing.reason));
    sections.push('### Agent outcomes');
    response.results.forEach(result => {
      sections.push(`#### ${result.agent}`, `Outcome: ${result.status}.${result.latency_ms === undefined ? '' : ` Latency: ${result.latency_ms} ms.`}`);
      if (result.answer) sections.push(literal(result.answer));
      if (result.error) sections.push('Error code', literal(result.error.code), 'Error message', literal(result.error.message));
      result.sources.forEach(source => sections.push('Agent source', literal(source)));
    });
    if (!response.results.length) sections.push('No agent results available.');
  });
  const content = `${sections.join('\n\n')}\n`;
  if (new TextEncoder().encode(content).length > 2 * 1024 * 1024) throw new Error('This report exceeds the download size limit.');
  return { filename: `opsbrain-investigation-${provenance.toLowerCase()}.md`, content };
}

export function downloadInvestigation(state, { document: doc = document, urls = URL, defer = setTimeout } = {}) {
  const report = investigationReport(state);
  const url = urls.createObjectURL(new Blob([report.content], { type: 'text/markdown;charset=utf-8' }));
  const link = doc.createElement('a');
  try {
    link.href = url; link.download = report.filename; link.hidden = true;
    doc.body.append(link); link.click();
  } finally {
    link.remove();
    defer(() => urls.revokeObjectURL(url), 30000);
  }
}

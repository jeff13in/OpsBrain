export const HISTORY_KEY = 'opsbrain.demo-history.v1';
export const HISTORY_TTL = 72 * 60 * 60 * 1000;
const MAX_RECORDS = 20;
const MAX_BYTES = 1000000;
const text = (value, max) => typeof value === 'string' && value.length <= max;

function validTurn(turn) {
  const reply = turn?.response;
  return text(turn?.question, 2000) && turn.question.trim().length >= 5 &&
    reply && ['ok', 'partial', 'error'].includes(reply.status) && text(reply.answer, 20000) &&
    Array.isArray(reply.sources) && reply.sources.length <= 20 && reply.sources.every(source => text(source, 2000)) &&
    Array.isArray(reply.results) && reply.results.length <= 4 && reply.results.every(result =>
      ['rag', 'monitoring', 'infra', 'code'].includes(result?.agent) && ['ok', 'error', 'timeout'].includes(result.status) &&
      (result.answer === null || text(result.answer, 20000)) && Array.isArray(result.sources) && result.sources.length <= 20 && result.sources.every(source => text(source, 2000)) &&
      (result.error === null || (text(result.error?.code, 100) && text(result.error?.message, 2000))));
}

function validRecord(record, now) {
  return record?.mode === 'demo' && typeof record.id === 'string' && /^[a-zA-Z0-9-]{1,80}$/.test(record.id) &&
    Number.isFinite(record.createdAt) && record.createdAt >= 0 && record.createdAt <= now &&
    Number.isFinite(record.updatedAt) && record.updatedAt >= record.createdAt && record.updatedAt <= now &&
    Array.isArray(record.turns) && record.turns.length > 0 && record.turns.length <= 20 && record.turns.every(validTurn);
}

function cleanTurn(turn) {
  const reply = turn.response;
  return { question: turn.question, response: {
    status: reply.status, answer: reply.answer, sources: [...reply.sources],
    results: reply.results.map(result => ({ agent: result.agent, status: result.status, answer: result.answer,
      sources: [...result.sources], error: result.error ? { code: result.error.code, message: result.error.message } : null })),
  } };
}

export function createHistory({ storage = () => window.localStorage, now = Date.now, id = () => crypto.randomUUID() } = {}) {
  let records = [];
  let memoryOnly = false;
  let warning = '';
  function unavailable() {
    memoryOnly = true;
    warning = 'Browser storage is unavailable or full. History changes stay in page memory; previously saved browser data may remain.';
  }
  function write() {
    if (memoryOnly) return;
    try {
      const value = JSON.stringify({ version: 1, records });
      if (value.length > MAX_BYTES) throw new Error('History too large');
      storage().setItem(HISTORY_KEY, value);
    } catch { unavailable(); }
  }
  function read() {
    const time = now();
    if (!memoryOnly) {
      try {
        const value = storage().getItem(HISTORY_KEY);
        if (value !== null) {
          let parsed;
          try {
            if (value.length > MAX_BYTES) throw new Error('History too large');
            parsed = JSON.parse(value);
            if (parsed?.version !== 1 || !Array.isArray(parsed.records) || parsed.records.length > MAX_RECORDS) throw new Error('Invalid history');
          } catch {
            parsed = { records: [] };
            warning = 'Invalid saved history was discarded. You can start a new demo conversation.';
          }
          const seen = new Set();
          records = parsed.records.filter(record => {
            if (!validRecord(record, time) || seen.has(record.id)) return false;
            seen.add(record.id);
            return true;
          });
          if (records.length !== parsed.records.length) warning = 'Invalid saved conversations were discarded.';
          if (warning) write();
        } else records = [];
      } catch { unavailable(); }
    }
    const retained = records.filter(record => record.createdAt + HISTORY_TTL > time);
    if (retained.length !== records.length) { records = retained; write(); }
    records.sort((a, b) => b.updatedAt - a.updatedAt);
    return records;
  }
  return {
    snapshot() { read(); return structuredClone({ records, persistent: !memoryOnly, warning }); },
    get(recordId) { return structuredClone(read().find(record => record.id === recordId) || null); },
    save(recordId, turns) {
      read();
      if (!Array.isArray(turns)) return null;
      const ready = turns.filter(turn => turn?.response);
      if (!ready.length || ready.length > 20 || !ready.every(validTurn)) return null;
      const completed = ready.map(cleanTurn);
      const existing = records.find(record => record.id === recordId);
      // Expired/deleted conversations cannot be silently re-created with old turns.
      if (recordId && !existing) return null;
      const time = now();
      const record = { id: existing?.id || id(), mode: 'demo', createdAt: existing?.createdAt ?? time, updatedAt: time, turns: completed };
      if (!validRecord(record, time)) return null;
      records = [record, ...records.filter(item => item.id !== record.id)].slice(0, MAX_RECORDS);
      write();
      return record.id;
    },
    remove(recordId) { read(); records = records.filter(record => record.id !== recordId); write(); },
    clear() { records = []; write(); },
  };
}

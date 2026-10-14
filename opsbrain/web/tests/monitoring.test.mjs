import test from 'node:test';
import assert from 'node:assert/strict';
import { createMonitoring, METRICS, sampleSnapshot } from '../public/monitoring.js';
import { metricChart, renderPage } from '../public/ui.js';

test('time windows select deterministic bounded synthetic samples', () => {
  for (const metric of METRICS) {
    const short = sampleSnapshot('populated', '15m')[metric.id];
    const long = sampleSnapshot('populated', '1h')[metric.id];
    assert.equal(short.length, 4);
    assert.equal(long.length, 12);
    assert.deepEqual(short, long.slice(-4));
    assert.ok(short.every(point => point.minutesAgo <= 15 && point.value <= metric.maximum));
    assert.notDeepEqual(short, sampleSnapshot('populated', '15m', 1)[metric.id]);
    assert.deepEqual(short, sampleSnapshot('populated', '15m', 2)[metric.id]);
  }
  assert.throws(() => sampleSnapshot('live', '15m'));
  assert.throws(() => sampleSnapshot('populated', 'unknown'));
});

test('partial and unavailable scenarios never invent zero-valued metrics', () => {
  const partial = sampleSnapshot('partial', '1h');
  assert.equal(partial.cpu.length, 12);
  assert.equal(partial.memory.length, 12);
  assert.deepEqual(partial.latency, []);
  for (const scenario of ['empty', 'error', 'disconnected']) {
    assert.ok(Object.values(sampleSnapshot(scenario, '15m')).every(points => points.length === 0));
  }
});

test('manual refresh has loading, duplicate prevention and a labelled generation time', async () => {
  let complete;
  let calls = 0;
  const monitor = createMonitoring({ now: () => '2026-10-11T12:00:00Z', load: () => { calls++; return new Promise(resolve => { complete = resolve; }); } });
  assert.equal(await monitor.refresh(), false);
  monitor.setActive(true);
  const pending = monitor.select('populated', '15m');
  assert.equal(monitor.snapshot().pending, true);
  assert.equal(monitor.snapshot().samples, null);
  assert.equal(await monitor.refresh(), false);
  assert.equal(calls, 1);
  complete(sampleSnapshot('populated', '15m'));
  await pending;
  assert.equal(monitor.snapshot().refreshedAt, '2026-10-11T12:00:00Z');
  assert.equal(monitor.snapshot().revision, 1);
  assert.equal(monitor.snapshot().pending, false);
});

test('changing options discards stale responses and deactivation cancels loading', async () => {
  const resolves = [];
  const monitor = createMonitoring({ load: () => new Promise(resolve => resolves.push(resolve)) });
  monitor.setActive(true);
  const first = monitor.select('populated', '15m');
  const second = monitor.select('partial', '1h');
  resolves[0](sampleSnapshot('populated', '15m'));
  assert.equal(await first, false);
  assert.equal(monitor.snapshot().pending, true);
  resolves[1](sampleSnapshot('partial', '1h'));
  await second;
  assert.deepEqual(monitor.snapshot().samples.latency, []);
  const third = monitor.refresh();
  monitor.setActive(false);
  resolves[2](sampleSnapshot('partial', '1h'));
  assert.equal(await third, false);
  assert.equal(monitor.snapshot().samples, null);
  assert.equal(monitor.snapshot().scenario, 'disconnected');
});

test('automatic refresh is opt-in, uses 30 seconds and stops on leaving the page', async () => {
  let tick;
  const cleared = [];
  let calls = 0;
  const monitor = createMonitoring({
    load: async (scenario, range) => { calls++; return sampleSnapshot(scenario, range); },
    schedule(callback, interval) { assert.equal(interval, 30000); tick = callback; return 7; },
    unschedule: id => cleared.push(id),
  });
  monitor.setActive(true);
  monitor.setAuto(true);
  assert.equal(monitor.snapshot().auto, false, 'Disconnected cannot auto-refresh');
  await monitor.select('populated', '15m');
  assert.equal(monitor.snapshot().auto, false);
  monitor.setAuto(true);
  tick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 2);
  monitor.setActive(false);
  assert.deepEqual(cleared, [7]);
  assert.equal(monitor.snapshot().auto, false);
  tick();
  assert.equal(calls, 2);
  monitor.setActive(true);
  assert.equal(monitor.snapshot().auto, false, 'Returning does not silently resume auto-refresh');
});

test('refresh failures clear old successes and stop automatic refresh', async () => {
  let fail = false;
  const monitor = createMonitoring({ load: async (scenario, range) => {
    if (fail) throw new Error('private dependency details');
    return sampleSnapshot(scenario, range);
  } });
  monitor.setActive(true);
  await monitor.select('populated', '15m');
  fail = true;
  await monitor.refresh();
  const state = monitor.snapshot();
  assert.equal(state.scenario, 'error');
  assert.equal(state.samples, null);
  assert.equal(state.refreshedAt, null);
  assert.equal(state.pending, false);
  const html = renderPage('monitoring', { monitoringState: state }).html;
  assert.doesNotMatch(html, /private dependency details|<polyline/);
});

test('charts have accessible descriptions, labelled tables and finite coordinates', () => {
  for (const metric of METRICS) {
    const points = sampleSnapshot('populated', '15m')[metric.id];
    const html = metricChart(metric, points);
    assert.match(html, /role="img" aria-labelledby=/);
    assert.match(html, /<title/);
    assert.match(html, /<desc/);
    assert.match(html, /<caption>/);
    assert.match(html, /scope="col"/);
    assert.equal((html.match(/scope="row"/g) || []).length, 4);
    assert.doesNotMatch(html, /NaN|Infinity/);
    for (const [, value] of html.matchAll(/points="([^"]+)"/g)) {
      assert.ok(value.split(/[ ,]/).every(part => Number.isFinite(Number(part))));
    }
  }
  for (const points of [[], null, [{ value: NaN, minutesAgo: 0 }, { value: 60, minutesAgo: 5 }], [{ value: 101, minutesAgo: 5 }, { value: 60, minutesAgo: 0 }]]) {
    const html = metricChart(METRICS[0], points);
    assert.match(html, /Metric unavailable/);
    assert.doesNotMatch(html, /<polyline/);
  }
});

test('monitoring rendering discloses provenance and hides charts for unavailable states', () => {
  assert.match(renderPage('monitoring').html, /No monitoring backend connected/);
  for (const scenario of ['populated', 'partial', 'empty', 'error', 'disconnected']) {
    const html = renderPage('monitoring', { monitoringState: { scenario, range: '15m', samples: sampleSnapshot(scenario, '15m'), pending: false, auto: false, refreshedAt: '2026-10-11T12:00:00Z' } }).html;
    assert.match(html, /All chart values are synthetic/);
    assert.match(html, /not a backend observation time/);
    assert.doesNotMatch(html, /badge-live/);
    assert.equal((html.match(/<polyline/g) || []).length, scenario === 'populated' ? 6 : scenario === 'partial' ? 5 : 0);
  }
});

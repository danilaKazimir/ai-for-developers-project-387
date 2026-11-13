import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { dirname, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const apiPort = 18000;
const webPort = 15173;
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
const timeout = 30_000;
const shutdown = new AbortController();
const processes = [];

for (const [signal, code] of [['SIGINT', 130], ['SIGTERM', 143]]) {
  process.on(signal, () => {
    process.exitCode = code;
    shutdown.abort(new Error(`Received ${signal}`));
  });
}

function start(name, command, args, env = process.env, persistent = false) {
  const child = spawn(command, args, { cwd: root, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const record = { name, child, persistent, logs: '', exited: false, result: undefined, error: undefined };
  processes.push(record);
  for (const stream of [child.stdout, child.stderr]) {
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => { record.logs = (record.logs + chunk).slice(-16_000); });
  }
  child.on('error', (error) => { record.error = error; });
  child.on('exit', (code, signal) => { record.result = { code, signal }; });
  child.on('close', () => { record.exited = true; });
  return record;
}

function assertRunning() {
  shutdown.signal.throwIfAborted();
  for (const record of processes) {
    if (record.error) throw new Error(`${record.name}: ${record.error.message}`);
    if (record.persistent && record.result) {
      throw new Error(`${record.name} exited unexpectedly (${record.result.signal ?? record.result.code})`);
    }
  }
}

function waitForExit(record, signal) {
  if (record.exited) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      record.child.off('close', onClose);
      signal.removeEventListener('abort', onAbort);
    };
    const onClose = () => { cleanup(); resolve(); };
    const onAbort = () => { cleanup(); reject(signal.reason); };
    record.child.once('close', onClose);
    signal.addEventListener('abort', onAbort, { once: true });
    if (signal.aborted) onAbort();
  });
}

async function run(name, args) {
  const record = start(name, 'uv', ['run', '--frozen', ...args]);
  await waitForExit(record, AbortSignal.any([shutdown.signal, AbortSignal.timeout(timeout)]));
  if (record.error) throw new Error(`${name}: ${record.error.message}`);
  if (record.result?.code !== 0) throw new Error(`${name} failed (${record.result?.signal ?? record.result?.code})`);
}

async function assertPortFree(port) {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', (error) => reject(new Error(`Port ${port} is unavailable: ${error.message}`)));
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(resolve));
  });
}

async function request(path) {
  return fetch(path, {
    signal: AbortSignal.any([shutdown.signal, AbortSignal.timeout(1_000)]),
    redirect: 'error',
  });
}

async function checkHealth(baseUrl) {
  const response = await request(`${baseUrl}/api/health`);
  assert.equal(response.status, 200, `${baseUrl}/api/health must return 200`);
  assert.deepEqual(await response.json(), { status: 'ok', database: 'ok' });
}

async function checkPage() {
  const response = await request(webUrl);
  assert.equal(response.status, 200, 'The frontend must return 200');
  assert.match(response.headers.get('content-type') ?? '', /text\/html/);
  const html = await response.text();
  assert.match(html, /<div\b[^>]*\bid=["']root["']/);
  assert.match(html, /<script\b(?=[^>]*\btype=["']module["'])(?=[^>]*\bsrc=["']\/src\/main\.tsx["'])[^>]*>/);
}

async function waitForReady() {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    assertRunning();
    try {
      await Promise.all([checkHealth(apiUrl), checkPage(), checkHealth(webUrl)]);
      assertRunning();
      return;
    } catch (error) {
      lastError = error;
    }
    assertRunning();
    await delay(200, undefined, { signal: shutdown.signal });
  }
  throw new Error(`Application was not ready within 30 seconds: ${lastError?.message}`);
}

function signalGroup(record, signal) {
  if (!record.child.pid) return;
  try {
    process.kill(-record.child.pid, signal);
  } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
}

function groupExists(record) {
  if (!record.child.pid) return false;
  try {
    process.kill(-record.child.pid, 0);
    return true;
  } catch (error) {
    if (error.code === 'ESRCH') return false;
    throw error;
  }
}

async function stopProcesses() {
  for (const record of processes) signalGroup(record, 'SIGTERM');
  const deadline = Date.now() + 3_000;
  while (processes.some(groupExists) && Date.now() < deadline) await delay(50);
  for (const record of processes) signalGroup(record, 'SIGKILL');
  await Promise.all(processes.map((record) => waitForExit(record, AbortSignal.timeout(3_000))));
}

try {
  if (!process.env.TEST_DATABASE_URL) throw new Error('TEST_DATABASE_URL is required; see README.md');
  await assertPortFree(apiPort);
  await assertPortFree(webPort);
  // Use SQLAlchemy's URL parser and the same database guards as the integration tests.
  await run('Test database validation and migrations', ['python', '-c', `
import os
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from backend.app.config import Settings

test_url = os.environ["TEST_DATABASE_URL"]
url = make_url(test_url)
if not url.database or not url.database.endswith("_test"):
    raise SystemExit("TEST_DATABASE_URL must use a dedicated database ending in _test")
app_url = os.environ.get("DATABASE_URL")
if app_url and url == make_url(app_url):
    raise SystemExit("TEST_DATABASE_URL must differ from DATABASE_URL")
Settings(database_url=test_url)
os.environ["DATABASE_URL"] = test_url
command.upgrade(Config("alembic.ini"), "head")
`]);
  assertRunning();
  const env = { ...process.env, DATABASE_URL: process.env.TEST_DATABASE_URL, API_PROXY_TARGET: apiUrl };
  start('API', 'uv', [
    'run', '--frozen', 'uvicorn', 'backend.app.main:create_app', '--factory',
    '--host', '127.0.0.1', '--port', String(apiPort),
  ], env, true);
  start('Vite', process.execPath, [
    'node_modules/vite/bin/vite.js', '--config', 'frontend/vite.config.ts',
    '--host', '127.0.0.1', '--port', String(webPort), '--strictPort',
  ], env, true);
  await waitForReady();
} catch (error) {
  process.exitCode ||= 1;
  console.error(`Smoke test failed: ${(shutdown.signal.reason ?? error).message}`);
} finally {
  try {
    await stopProcesses();
  } catch (error) {
    process.exitCode ||= 1;
    console.error(`Smoke test cleanup failed: ${error.message}`);
  }
  if (process.exitCode) {
    for (const record of processes) {
      if (record.logs) console.error(`\n--- ${record.name} ---\n${record.logs}`);
    }
  } else {
    console.log('Smoke test passed: API, PostgreSQL, frontend HTML and Vite proxy are available.');
  }
}

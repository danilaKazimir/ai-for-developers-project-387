import { execFileSync, spawn } from 'node:child_process';

const database = process.env.TEST_DATABASE_URL;
if (!database || !new URL(database).pathname.endsWith('_test') || database === process.env.DATABASE_URL) {
  throw new Error('Use a dedicated TEST_DATABASE_URL ending in _test, different from DATABASE_URL.');
}
const env = { ...process.env, DATABASE_URL: database };
execFileSync('uv', ['run', '--frozen', 'alembic', 'upgrade', 'head'], { env, stdio: 'inherit' });
// Every full-stack profile starts from empty data in its dedicated test database.
execFileSync('uv', ['run', '--frozen', 'python', '-c', `
import os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.begin() as connection:
    connection.execute(text('DELETE FROM bookings'))
    connection.execute(text('DELETE FROM event_types'))
    connection.execute(text("UPDATE calendars SET timezone = 'Europe/Moscow' WHERE id = 1"))
engine.dispose()
`], { env, stdio: 'inherit' });
const api = spawn('uv', ['run', '--frozen', 'uvicorn', 'backend.app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '18001'], { env, stdio: 'inherit' });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => api.kill(signal));
api.on('exit', (code) => process.exit(code ?? 1));

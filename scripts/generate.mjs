import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const check = process.argv.includes('--check');
const outputRoot = check ? mkdtempSync(join(tmpdir(), 'call-calendar-generation-')) : root;
const generated = [
  'api/generated',
  'frontend/src/api/generated',
  'backend/app/generated/models.py',
];

function run(command, args) {
  execFileSync(command, args, {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, GENERATED_ROOT: outputRoot },
  });
}

function files(path) {
  if (!existsSync(path)) return [];
  const entries = readdirSync(path, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const child = join(path, entry.name);
    return entry.isDirectory() ? files(child) : [child];
  });
}

function snapshot(base) {
  const result = new Map();
  for (const path of generated) {
    const absolute = join(base, path);
    const paths = path.endsWith('.py') ? (existsSync(absolute) ? [absolute] : []) : files(absolute);
    for (const file of paths) result.set(relative(base, file), readFileSync(file));
  }
  return result;
}

try {
  mkdirSync(join(outputRoot, 'api/generated'), { recursive: true });
  mkdirSync(join(outputRoot, 'backend/app/generated'), { recursive: true });
  if (check) {
    // Match Ruff settings when codegen formats models outside the repository.
    cpSync(join(root, 'pyproject.toml'), join(outputRoot, 'pyproject.toml'));
    mkdirSync(join(outputRoot, 'frontend/src/api'), { recursive: true });
    cpSync(join(root, 'frontend/src/api/http.ts'), join(outputRoot, 'frontend/src/api/http.ts'));
  }
  run('npx', ['--no-install', 'tsp', 'compile', 'api', '--output-dir', join(outputRoot, 'api/generated')]);
  run('npx', ['--no-install', 'orval', '--config', 'orval.config.ts']);
  run('uv', [
    'run', '--frozen', 'datamodel-codegen',
    '--input', join(outputRoot, 'api/generated/openapi.yaml'),
    '--input-file-type', 'openapi',
    '--output', join(outputRoot, 'backend/app/generated/models.py'),
    '--output-model-type', 'pydantic_v2.BaseModel',
    '--target-python-version', '3.13',
    '--disable-timestamp',
    '--use-union-operator',
    '--use-standard-collections',
    '--use-schema-description',
    '--field-constraints',
    '--extra-fields', 'forbid',
    '--formatters', 'ruff-format',
  ]);
  if (check) {
    const saved = snapshot(root);
    const fresh = snapshot(outputRoot);
    const names = new Set([...saved.keys(), ...fresh.keys()]);
    const changed = [...names].filter((name) =>
      !saved.has(name) || !fresh.has(name) || !saved.get(name).equals(fresh.get(name)),
    );
    if (changed.length > 0) {
      throw new Error(`Generated files are stale. Run mise run generate:\n${changed.join('\n')}`);
    }
    console.log('Generated files are up to date.');
  }
} finally {
  if (check) rmSync(outputRoot, { recursive: true, force: true });
}


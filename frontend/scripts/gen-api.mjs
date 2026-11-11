// Regenerate src/api/schema.d.ts from the backend's OpenAPI schema (no running server needed).
//   npm run gen:api
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const root = resolve(frontend, '..')
const python = [join(root, '.venv', 'Scripts', 'python.exe'), join(root, '.venv', 'bin', 'python')].find(existsSync) ?? 'python'
const spec = join(frontend, 'src', 'api', 'openapi.json')

execFileSync(python, ['-m', 'backend.scripts.export_openapi', spec], { cwd: root, stdio: 'inherit' })
execFileSync('npx', ['-y', 'openapi-typescript@7.13.0', spec, '-o', join(frontend, 'src', 'api', 'schema.d.ts')], {
  cwd: frontend,
  stdio: 'inherit',
  shell: process.platform === 'win32',
})

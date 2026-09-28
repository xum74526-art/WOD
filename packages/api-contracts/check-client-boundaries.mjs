import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', '..')

function filesUnder(relative, extensions = ['.ts', '.tsx', '.vue']) {
  const base = path.join(root, relative)
  const result = []
  for (const entry of fs.readdirSync(base, { withFileTypes: true })) {
    const child = path.join(base, entry.name)
    if (entry.isDirectory()) result.push(...filesUnder(path.relative(root, child), extensions))
    else if (extensions.some(extension => child.endsWith(extension))) result.push(child)
  }
  return result
}

const rules = [
  {
    files: [
      ...filesUnder('apps/ios/src'),
      path.join(root, 'apps/ios/vite.config.ts'),
      ...filesUnder('apps/android/src'),
      path.join(root, 'apps/android/vite.config.ts'),
    ],
    patterns: [
      ['VITE_WOD_APP_API_BASE', 'legacy mobile API environment alias'],
      ['WOD_H5_API_TARGET', 'legacy H5 API environment alias'],
      ['/payments/qixiangpay/', 'legacy payment route used by a current client'],
      ['DATABASE_URL', 'client-side database configuration'],
    ],
  },
  {
    files: [
      ...filesUnder('apps/web/app'),
      ...filesUnder('apps/web/components'),
      ...filesUnder('apps/web/lib').filter(file => !file.endsWith('api-adapter.ts')),
    ],
    patterns: [
      ['/api/v1/mobile', 'legacy platform-specific Web BFF route'],
      ['/payments/qixiangpay/', 'legacy payment route used by a current client'],
      ['DATABASE_URL', 'client-side database configuration'],
    ],
  },
  {
    files: filesUnder('services/collector/collector', ['.py']),
    patterns: [
      ['DATABASE_URL', 'Collector database configuration'],
      ['sqlalchemy', 'Collector database client'],
      ['psycopg', 'Collector database client'],
      ['asyncpg', 'Collector database client'],
      ['sqlite3', 'Collector database client'],
      ['pymongo', 'Collector database client'],
    ],
  },
]

const violations = []
for (const rule of rules) {
  for (const file of rule.files) {
    const source = fs.readFileSync(file, 'utf8')
    for (const [pattern, reason] of rule.patterns) {
      if (source.includes(pattern)) violations.push(`${path.relative(root, file)}: ${reason} (${pattern})`)
    }
  }
}

if (violations.length) {
  console.error('Client boundary check failed:')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exit(1)
}

console.log('Boundary check passed: Collector, Web, iOS and Android use the canonical cloud API boundary.')

import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const ts = require(path.join(root, 'apps/mobile/node_modules/typescript'))
const openapi = JSON.parse(fs.readFileSync(path.join(here, 'openapi.json'), 'utf8'))
const mobileRoot = path.join(root, 'apps', 'mobile', 'src')

const apiRoutes = []
for (const [route, operations] of Object.entries(openapi.paths)) {
  if (!route.startsWith('/api/v1/')) continue
  for (const method of Object.keys(operations)) {
    if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue
    const relative = route.slice('/api/v1'.length)
    const expression = relative
      .split('/')
      .map(segment => /^\{[^}]+\}$/.test(segment) ? '[^/]+' : segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .join('/')
    apiRoutes.push({ method: method.toUpperCase(), route, pattern: new RegExp(`^${expression}$`) })
  }
}

function sourceFiles(directory) {
  const result = []
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name)
    if (entry.isDirectory()) result.push(...sourceFiles(full))
    else if (entry.name.endsWith('.ts') || entry.name.endsWith('.vue')) result.push(full)
  }
  return result
}

function scriptText(file) {
  const content = fs.readFileSync(file, 'utf8')
  if (!file.endsWith('.vue')) return content
  const matches = [...content.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)]
  return matches.map(match => match[1]).join('\n')
}

function propertyName(node) {
  return node?.name && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name))
    ? node.name.text
    : ''
}

function stringValue(node, source) {
  if (!node) return null
  if (ts.isStringLiteralLike(node)) return node.text
  if (ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) {
    let value = node.head.text
    for (const span of node.templateSpans) value += `{param}${span.literal.text}`
    return value
  }
  return null
}

function inspect(file) {
  const sourceText = scriptText(file)
  const source = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const calls = []
  const violations = []
  const location = node => ({
    file: path.relative(root, file),
    line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
  })
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const callee = ts.isIdentifier(node.expression) ? node.expression.text : ''
      if (['request', 'requestEnvelope', 'upload'].includes(callee) && node.arguments.length) {
        const options = node.arguments[0]
        if (!ts.isObjectLiteralExpression(options)) {
          violations.push({ ...location(node), reason: `${callee} options must be an inline object` })
        } else {
          let url = null
          let method = callee === 'upload' ? 'POST' : 'GET'
          let methodIsDynamic = false
          for (const property of options.properties) {
            if (!ts.isPropertyAssignment(property)) continue
            const name = propertyName(property)
            if (name === 'url') url = stringValue(property.initializer, source)
            if (name === 'method') {
              const staticMethod = stringValue(property.initializer, source)
              methodIsDynamic = !staticMethod
              method = staticMethod || method
            }
          }
          if (!url) violations.push({ ...location(node), reason: `${callee} URL must be a static relative path` })
          else if (!url.startsWith('/')) violations.push({ ...location(node), reason: `${callee} URL must use the centralized /api/v1 base` })
          else if (methodIsDynamic) violations.push({ ...location(node), reason: `${callee} method must be statically auditable` })
          else calls.push({ ...location(node), method: method.toUpperCase(), url: url.split('?')[0] })
        }
      }

      const isRawFetch = callee === 'fetch'
      const isRawUniRequest = ts.isPropertyAccessExpression(node.expression)
        && ts.isIdentifier(node.expression.expression)
        && node.expression.expression.text === 'uni'
        && ['request', 'uploadFile', 'downloadFile'].includes(node.expression.name.text)
      const centralTransport = path.relative(root, file) === 'apps/mobile/src/api/request.ts'
      if ((isRawFetch || isRawUniRequest) && !centralTransport) {
        violations.push({ ...location(node), reason: 'raw network access must go through api/request.ts' })
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return { calls, violations }
}

const inspection = sourceFiles(mobileRoot).map(inspect)
const calls = inspection.flatMap(result => result.calls)
const violations = inspection.flatMap(result => result.violations)
const missing = calls.filter(call => !apiRoutes.some(route => (
  route.method === call.method && route.pattern.test(call.url.replaceAll('{param}', 'value'))
)))

if (missing.length || violations.length) {
  console.error(`Mobile API contract check failed: ${missing.length} missing route(s), ${violations.length} unauditable request(s).`)
  for (const call of missing) console.error(`${call.method} ${call.url}  ${call.file}:${call.line}`)
  for (const issue of violations) console.error(`${issue.reason}  ${issue.file}:${issue.line}`)
  process.exit(1)
}

console.log(`Mobile API contract check passed: ${calls.length} request(s) use canonical /api/v1 routes.`)

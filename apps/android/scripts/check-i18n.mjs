import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = path.resolve(import.meta.dirname, '..')
const srcRoot = path.join(root, 'src')

function sourceFile(file) {
  return ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true)
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text
  return null
}

function stringValue(node) {
  return ts.isStringLiteralLike(node) || ts.isNoSubstitutionTemplateLiteral(node) ? node.text : null
}

function readStringMap(file, variableName) {
  const result = new Map()
  const visit = (node) => {
    if (ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.name.text === variableName
      && node.initializer
      && ts.isObjectLiteralExpression(node.initializer)) {
      for (const property of node.initializer.properties) {
        if (!ts.isPropertyAssignment(property)) continue
        const key = propertyName(property.name)
        const value = stringValue(property.initializer)
        if (key != null && value != null) result.set(key, value)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile(file))
  return result
}

function walk(directory, extensions, output = []) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) walk(target, extensions, output)
    else if (extensions.some((extension) => entry.name.endsWith(extension))) output.push(target)
  }
  return output
}

function lineOf(source, index) {
  return source.slice(0, index).split(/\r?\n/).length
}

const storeFile = path.join(srcRoot, 'store', 'i18n.ts')
const generatedFile = path.join(srcRoot, 'store', 'i18n_generated.ts')
const zh = readStringMap(storeFile, 'ZH')
const en = readStringMap(storeFile, 'EN')
const extraEn = readStringMap(storeFile, 'EXTRA_EN')
const zhGenerated = readStringMap(generatedFile, 'ZH_GEN')
const enGenerated = readStringMap(generatedFile, 'EN_GEN')
const errors = []

for (const key of zh.keys()) {
  if (!en.has(key)) errors.push(`EN is missing semantic key: ${key}`)
}
for (const key of en.keys()) {
  if (!zh.has(key)) errors.push(`ZH is missing semantic key: ${key}`)
}
for (const key of zhGenerated.keys()) {
  if (!enGenerated.has(key)) errors.push(`EN_GEN is missing generated key: ${key}`)
}
for (const key of enGenerated.keys()) {
  if (!zhGenerated.has(key)) errors.push(`ZH_GEN is missing generated key: ${key}`)
}

const translatedChinese = new Set(extraEn.keys())
for (const [key, value] of zh) if (en.has(key)) translatedChinese.add(value)
for (const [key, value] of zhGenerated) if (enGenerated.has(key)) translatedChinese.add(value)
const semanticKeys = new Set([...zh.keys(), ...en.keys(), ...zhGenerated.keys(), ...enGenerated.keys()])
const appFiles = walk(srcRoot, ['.vue', '.ts']).filter((file) => !file.endsWith('store\\i18n.ts') && !file.endsWith('store\\i18n_generated.ts'))

for (const file of appFiles) {
  const source = fs.readFileSync(file, 'utf8')
  const relative = path.relative(root, file)
  const callPattern = /\b(?:t|tr)\(\s*(['"])(.*?)\1/g
  for (const match of source.matchAll(callPattern)) {
    const key = match[2]
    const hasChinese = /[\u3400-\u9fff]/.test(key)
    const looksSemantic = /^[A-Za-z][A-Za-z0-9_.-]*$/.test(key)
    if (hasChinese && !translatedChinese.has(key)) {
      errors.push(`${relative}:${lineOf(source, match.index)} untranslated Chinese literal: ${key}`)
    } else if (looksSemantic && !semanticKeys.has(key)) {
      errors.push(`${relative}:${lineOf(source, match.index)} unknown semantic key: ${key}`)
    }
  }

  if (!file.endsWith('.vue')) continue
  const template = source.match(/<template>([\s\S]*?)<\/template>/)?.[1] || ''
  const visible = template.replace(/<!--[\s\S]*?-->/g, '')
  const textPattern = />([^<]+)</g
  for (const match of visible.matchAll(textPattern)) {
    const raw = match[1].replace(/{{[\s\S]*?}}/g, '').trim()
    if (/[\u3400-\u9fff]/.test(raw)) {
      errors.push(`${relative}:${lineOf(source, source.indexOf(match[0]))} raw template text: ${raw}`)
    }
  }
  const nativePlaceholderPattern = /<(?:input|textarea)\b[^>]*?(?<!:)placeholder\s*=\s*(['"])([^'"]*[\u3400-\u9fff][^'"]*)\1/gi
  for (const match of visible.matchAll(nativePlaceholderPattern)) {
    errors.push(`${relative}:${lineOf(source, source.indexOf(match[0]))} raw native placeholder: ${match[2]}`)
  }
}

if (errors.length) {
  console.error(`i18n audit failed with ${errors.length} issue(s):`)
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log(`i18n audit passed: ${zh.size} semantic keys, ${zhGenerated.size} generated keys, ${appFiles.length} source files checked.`)

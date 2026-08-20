import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const manifestPath = path.join(root, 'src', 'manifest.json')
const envPath = path.join(root, '.env.example')
const privacyPath = path.join(root, 'src', 'nativeResources', 'ios', 'PrivacyInfo.xcprivacy')
const errors = []
const warnings = []

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
const appPlus = manifest['app-plus'] || {}
const ios = appPlus.distribute?.ios || {}
const privacy = ios.privacyDescription || {}
const requiredPrivacyKeys = [
  'NSPhotoLibraryUsageDescription',
  'NSCameraUsageDescription',
  'NSMicrophoneUsageDescription',
]

if (ios.devices !== 'iphone') errors.push('iOS devices must be iphone for the first release')
if (!/^\d+(\.\d+)?$/.test(String(ios.deploymentTarget || ''))) errors.push('iOS deploymentTarget is missing')
if (!String(ios.urltypes || '').split(',').map(value => value.trim()).includes('kai')) errors.push('kai URL Scheme is missing')
for (const key of requiredPrivacyKeys) {
  if (!String(privacy[key] || '').trim()) errors.push(`Missing iOS privacy purpose string: ${key}`)
}

const iconRelative = appPlus.distribute?.icons?.ios?.appstore
const iconPath = path.join(root, 'src', String(iconRelative || ''))
if (!iconRelative || !fs.existsSync(iconPath)) {
  errors.push('iOS App Store icon is missing')
} else {
  const png = fs.readFileSync(iconPath)
  const validPng = png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  if (!validPng || png.length < 24) errors.push('iOS App Store icon is not a valid PNG')
  else {
    const width = png.readUInt32BE(16)
    const height = png.readUInt32BE(20)
    if (width !== 1024 || height !== 1024) errors.push(`iOS App Store icon must be 1024x1024, got ${width}x${height}`)
  }
}

if (!fs.existsSync(privacyPath)) errors.push('PrivacyInfo.xcprivacy is missing')
else {
  const content = fs.readFileSync(privacyPath, 'utf8')
  if (!content.includes('<key>NSPrivacyTracking</key>') || !content.includes('<false/>')) {
    errors.push('PrivacyInfo.xcprivacy must explicitly declare tracking false')
  }
}

const envExample = fs.readFileSync(envPath, 'utf8')
if (!envExample.includes('VITE_KAI_IOS_DISTRIBUTION=app-store')) errors.push('Default iOS distribution mode must be app-store')
if (!String(manifest.appid || '').trim()) warnings.push('DCloud AppID is empty; cloud packaging will remain unavailable')
if (String(ios.appid || '') === 'com.example.kai') warnings.push('Replace the example iOS Bundle ID before signing')

if (errors.length) {
  errors.forEach(message => console.error(`ERROR: ${message}`))
  process.exit(1)
}
warnings.forEach(message => console.warn(`WARN: ${message}`))
console.log('iOS source configuration check passed.')

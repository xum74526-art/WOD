#!/usr/bin/env node

const [, , pageNeedle = '', expression = 'document.body.innerText'] = process.argv
const pages = await fetch('http://127.0.0.1:9222/json/list').then(response => response.json())
const page = pages.find(item => item.type === 'page' && item.title.includes(pageNeedle))

if (!page) {
  console.error(`No Android WebView page matched: ${pageNeedle}`)
  console.error(pages.map(item => item.title).join('\n'))
  process.exit(1)
}

const socket = new WebSocket(page.webSocketDebuggerUrl)
const response = await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error('CDP evaluation timed out')), 10_000)
  socket.addEventListener('open', () => {
    socket.send(JSON.stringify({
      id: 1,
      method: 'Runtime.evaluate',
      params: { expression, awaitPromise: true, returnByValue: true },
    }))
  })
  socket.addEventListener('message', event => {
    const message = JSON.parse(String(event.data))
    if (message.id !== 1) return
    clearTimeout(timeout)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
  })
  socket.addEventListener('error', reject)
})

socket.close()
const result = response?.result
if (result?.exceptionDetails) {
  console.error(JSON.stringify(result.exceptionDetails, null, 2))
  process.exit(1)
}
if (Object.prototype.hasOwnProperty.call(result || {}, 'value')) {
  const value = result.value
  process.stdout.write(typeof value === 'string' ? value : `${JSON.stringify(value, null, 2)}\n`)
} else {
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
}

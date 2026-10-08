import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const clients = process.argv[2] ? [process.argv[2]] : ['ios', 'android'];
assert.ok(clients.every(client => ['ios', 'android'].includes(client)), 'Expected ios or android');

function rejectsDepth(operation) {
  assert.throws(operation, error => error instanceof SyntaxError && error.code === 'ERR_BRACES_MAX_DEPTH');
}

function deepAst(depth) {
  const ast = { type: 'root', nodes: [] };
  let node = ast;
  for (let index = 0; index < depth; index++) {
    const child = { type: 'paren', nodes: [], parent: node };
    node.nodes.push(child);
    node = child;
  }
  node.nodes.push({ type: 'text', value: 'a' });
  return ast;
}

for (const client of clients) {
  const clientRoot = join(root, 'apps', client);
  const require = createRequire(join(clientRoot, 'package.json'));
  const braces = require('braces');

  test(`${client}: every installed braces copy uses the reviewed local patch`, () => {
    const lock = JSON.parse(readFileSync(join(clientRoot, 'package-lock.json'), 'utf8'));
    const locations = Object.keys(lock.packages).filter(path => path.endsWith('node_modules/braces'));
    assert.ok(locations.length > 0, 'The build still uses braces and must exercise this guard');
    for (const location of locations) {
      const entry = lock.packages[location];
      assert.equal(entry.resolved, 'file:../../packages/braces');
      const installed = join(clientRoot, location);
      const metadata = JSON.parse(readFileSync(join(installed, 'package.json'), 'utf8'));
      assert.equal(metadata.name, '@kai/braces');
      assert.equal(metadata.version, '3.0.3-kai.1');
      for (const file of ['index.js', ...readdirSync(join(root, 'packages/braces/lib')).map(name => `lib/${name}`)]) {
        assert.equal(readFileSync(join(installed, file), 'utf8'), readFileSync(join(root, 'packages/braces', file), 'utf8'), `${location}/${file} is stale`);
      }
      // Both callers must resolve the patched copy, including any nested installs.
      const installedRequire = createRequire(join(installed, 'index.js'));
      rejectsDepth(() => installedRequire('./index.js').compile('{'.repeat(4000) + 'a' + '}'.repeat(4000)));
    }
    for (const caller of ['micromatch', 'chokidar']) {
      const callerRequire = createRequire(require.resolve(caller));
      assert.equal(callerRequire('braces/package.json').name, '@kai/braces');
    }
  });

  test(`${client}: ordinary globs, ranges, escaping and deduplication remain compatible`, () => {
    assert.deepEqual(braces('src/{pages,utils}/**/*.{ts,vue}'), ['src/(pages|utils)/**/*.(ts|vue)']);
    assert.deepEqual(braces.expand('a/{b,{c,d}}/{01..03}'), [
      'a/b/01', 'a/b/02', 'a/b/03', 'a/c/01', 'a/c/02', 'a/c/03', 'a/d/01', 'a/d/02', 'a/d/03'
    ]);
    assert.deepEqual(braces(['{a,b}', '{b,c}'], { expand: true, nodupes: true }), ['a', 'b', 'c']);
    assert.equal(braces.stringify(braces.parse('a/{b,c}/d')), 'a/{b,c}/d');
    assert.equal(braces.compile('a/\\{b,c\\}/d'), 'a/{b,c}/d');
    const micromatch = require('micromatch');
    assert.deepEqual(micromatch(['src/a.ts', 'src/b.vue', 'src/c.css'], 'src/*.{ts,vue}'), ['src/a.ts', 'src/b.vue']);
  });

  test(`${client}: CVE-2026-93687 patterns cannot exhaust parser or walker stacks`, () => {
    const patterns = [
      '{'.repeat(4000) + 'a' + '}'.repeat(4000),
      '('.repeat(4000) + 'a' + ')'.repeat(4000),
      '{('.repeat(2000) + 'a' + ')}'.repeat(2000),
      '{'.repeat(4000) + 'a',
      '('.repeat(4000) + 'a'
    ];
    for (const pattern of patterns) {
      for (const method of [braces, braces.create, braces.parse, braces.compile, braces.expand, braces.stringify]) {
        rejectsDepth(() => method(pattern));
        rejectsDepth(() => method(pattern, { maxDepth: Infinity, maxLength: 10000 }));
      }
      rejectsDepth(() => braces([pattern], { expand: true }));
    }
  });

  test(`${client}: caller-supplied deep and cyclic ASTs are checked before recursion`, () => {
    for (const name of ['compile', 'expand', 'stringify']) {
      rejectsDepth(() => braces[name](deepAst(4000)));
      const cycle = { type: 'root', nodes: [] };
      cycle.nodes.push(cycle);
      rejectsDepth(() => braces[name](cycle));
      // Direct lib imports must have the same protection as the public facade.
      rejectsDepth(() => require(`braces/lib/${name}`)(deepAst(4000)));
    }
    const parentCycle = { type: 'paren', nodes: [{ type: 'paren', nodes: [] }] };
    parentCycle.parent = parentCycle;
    rejectsDepth(() => braces.expand(parentCycle));
  });

  test(`${client}: depth ceiling accepts normal nesting and ignores escaped or quoted braces`, () => {
    for (const name of ['parse', 'compile', 'expand', 'stringify']) {
      assert.doesNotThrow(() => braces[name]('{'.repeat(100) + 'a' + '}'.repeat(100)));
      assert.doesNotThrow(() => braces[name]('('.repeat(100) + 'a' + ')'.repeat(100)));
      rejectsDepth(() => braces[name]('{'.repeat(101) + 'a' + '}'.repeat(101)));
    }
    const quoted = '"' + '{'.repeat(2000) + 'a' + '}'.repeat(2000) + '"';
    assert.equal(braces.compile(quoted), quoted.slice(1, -1));
    assert.equal(braces.compile('\\{'.repeat(500)), '{'.repeat(500));
    assert.equal(braces.compile('[' + '{'.repeat(500) + ']'), '[' + '{'.repeat(500) + ']');
  });

  test(`${client}: existing input length and expansion limits still apply`, () => {
    assert.throws(() => braces.compile('a'.repeat(10001)), /exceeds max characters/);
    assert.throws(() => braces.compile('abcd', { maxLength: 3 }), /exceeds max characters/);
    assert.throws(() => braces.expand('{1..10000}'), /exceeds range limit/);
  });
}

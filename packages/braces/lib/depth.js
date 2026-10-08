'use strict';

// Keep the recursive upstream walkers far below the Node.js stack limit.
// This is a hard ceiling: caller options must not disable the security bound.
const MAX_DEPTH = 100;

const assertDepth = depth => {
  if (depth > MAX_DEPTH) {
    const error = new SyntaxError(`Brace pattern nesting exceeds maximum depth (${MAX_DEPTH})`);
    error.code = 'ERR_BRACES_MAX_DEPTH';
    throw error;
  }
};

// Public compile/expand/stringify also accept caller-created ASTs. Validate
// those iteratively, including cycles in nodes, before any recursive walker.
// Parent/prev links are deliberately not followed; parsed ASTs contain them.
const assertAstDepth = ast => {
  const pending = [{ node: ast, depth: 0 }];
  while (pending.length) {
    const { node, depth } = pending.pop();
    if (node && node.nodes) {
      assertDepth(depth);
      for (const child of node.nodes) {
        pending.push({ node: child, depth: depth + 1 });
      }
    }
  }
};

module.exports = { assertDepth, assertAstDepth };

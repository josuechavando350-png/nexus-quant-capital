// Execute only the upstream tracer factory and its exact serialization function.
// No parser/ValidationManager dependency shims and no network API in the VM.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require(process.argv[2]);
const out = process.argv[3];
if (ts.version !== '4.9.5') throw new Error('Unexpected cached TypeScript');
const input = fs.readFileSync(path.join(out, 'BundlerCollectorTracer.ts'), 'utf8');
const source = fs.readFileSync(path.join(out, 'GethTracer.ts'), 'utf8');
const ast = ts.createSourceFile('GethTracer.ts', source, ts.ScriptTarget.ES2017, true);
const fn = ast.statements.find(s => ts.isFunctionDeclaration(s) && s.name.text === 'getTracerBodyString');
if (!fn) throw new Error('Upstream serializer missing');
const compile = s => ts.transpileModule(s, {compilerOptions: {
  target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.CommonJS
}}).outputText;
const code = compile(input) + '\n' + compile(fn.getText(ast));
if (/require\(/.test(code)) throw new Error('Unexpected runtime dependency');
const context = {exports: {}};
vm.runInNewContext(code, context, {timeout: 2000});
const tracer = context.exports.getTracerBodyString(context.exports.bundlerCollectorTracer);
fs.writeFileSync(path.join(out, 'tracer.js'), tracer + '\n');
fs.writeFileSync(path.join(out, 'tracer-transpiled.cjs'), code);

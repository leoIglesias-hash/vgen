"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var frontend = path.join(__dirname, "..", "frontend");
var files = fs.readdirSync(frontend).filter(function (name) {
  return /\.(?:js|html)$/.test(name);
}).sort();

function scriptsFromHtml(source) {
  var scripts = [], match;
  var pattern = /<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi;
  while ((match = pattern.exec(source)) !== null) {
    if (/\bsrc\s*=/.test(match[0])) { continue; }
    scripts.push(match[1]);
  }
  return scripts;
}

/* Quita comentarios y strings clasicos para que palabras documentales o un backtick
 * citado no parezcan sintaxis ejecutable. Un backtick real se conserva y se rechaza. */
function codeSurface(source) {
  var output = "", index = 0, length = source.length, quote, ch, next;
  while (index < length) {
    ch = source.charAt(index);
    next = source.charAt(index + 1);
    if (ch === "/" && next === "/") {
      output += "  "; index += 2;
      while (index < length && source.charAt(index) !== "\n") {
        output += " "; index++;
      }
      continue;
    }
    if (ch === "/" && next === "*") {
      output += "  "; index += 2;
      while (index < length &&
             !(source.charAt(index) === "*" && source.charAt(index + 1) === "/")) {
        output += source.charAt(index) === "\n" ? "\n" : " "; index++;
      }
      if (index < length) { output += "  "; index += 2; }
      continue;
    }
    if (ch === "\"" || ch === "'") {
      quote = ch; output += " "; index++;
      while (index < length) {
        ch = source.charAt(index);
        if (ch === "\\") {
          output += "  "; index += 2; continue;
        }
        output += ch === "\n" ? "\n" : " "; index++;
        if (ch === quote) { break; }
      }
      continue;
    }
    output += ch; index++;
  }
  return output;
}

function checkES5(label, source) {
  var code = codeSurface(source);
  assert.strictEqual(/\b(?:let|const|class|async|await|import|export|yield)\b|=>|`|\.\.\.|\?\.|\?\?/.test(code), false,
    label + " usa sintaxis posterior al piso ES5");
  assert.strictEqual(/\bfor\s*\([^)]*\bof\b/.test(code), false,
    label + " usa for-of, fuera del piso ES5");
  assert.strictEqual(/\bvar\s*[\{\[]|\bfunction\b[^\(]*\(\s*[\{\[]|\bfunction\b[^\(]*\([^\)]*=[^=]/.test(code), false,
    label + " usa destructuring o parametros por defecto, fuera del piso ES5");
  assert.strictEqual(/\b(?:fetch|Promise|WebAssembly|OffscreenCanvas|SharedArrayBuffer)\b/.test(code), false,
    label + " exige una API fuera del contrato legacy");
  assert.strictEqual(/\b(?:serviceWorker|WebGL2RenderingContext|URLSearchParams|BigInt)\b/.test(code), false,
    label + " exige una API opcional no permitida en produccion");
  assert.strictEqual(/\bObject\.assign\b|\bArray\.from\b|\.(?:includes|startsWith|endsWith)\s*\(/.test(code), false,
    label + " usa helpers modernos sin fallback legacy");
  // W-01: metodos de TypedArray posteriores al primer soporte (subarray y set
  // son el piso permitido; fill/copyWithin/slice faltan en WebViews 2012-2015).
  assert.strictEqual(/\.(?:fill|copyWithin)\s*\(/.test(code), false,
    label + " usa TypedArray fill/copyWithin, ausentes en WebViews legacy");
  assert.strictEqual(/\b(?:Map|Set|WeakMap|WeakSet|Symbol|Proxy|Reflect)\s*\(|\bnew\s+(?:Map|Set|WeakMap|WeakSet|Proxy)\b/.test(code), false,
    label + " usa colecciones/reflexion ES2015 sin fallback");
  assert.strictEqual(/\bObject\.(?:keys|values|entries|freeze|defineProperty|create)\s*\(/.test(code), false,
    label + " usa Object.* moderno sin fallback legacy");
  assert.strictEqual(/\bArray\.(?:isArray|of)\s*\(/.test(code), false,
    label + " usa Array.isArray/of sin fallback legacy");
  assert.strictEqual(/\bMath\.(?:trunc|imul|clz32|log2|sign|fround|cbrt|hypot)\s*\(/.test(code), false,
    label + " usa Math.* posterior a ES5");
  assert.strictEqual(/\bUint8ClampedArray\b/.test(code), false,
    label + " construye Uint8ClampedArray, ausente en WebKit viejo");
  assert.strictEqual(/\.(?:repeat|padStart|padEnd|trimStart|trimEnd|codePointAt|normalize)\s*\(/.test(code), false,
    label + " usa String.prototype posterior a ES5");
  assert.strictEqual(/\.(?:dataset|classList)\b|\.(?:matches|closest)\s*\(/.test(code), false,
    label + " usa APIs DOM sin soporte en WebViews legacy");
  assert.strictEqual(/\bJSON\s*\./.test(code), false,
    label + " usa JSON.*, prohibido por contrato (parseo manual acotado)");
  // Nota: la coma final en llamadas no puede detectarse sobre esta superficie
  // (los strings blanqueados dejan "f(x,   )" y darian falso positivo).
  assert.strictEqual(/\bget\s+\w+\s*\(\s*\)\s*\{|\bset\s+\w+\s*\(\s*\w+\s*\)\s*\{/.test(code), false,
    label + " define getters/setters de objeto, fuera del piso permitido");
  assert.doesNotThrow(function () { new Function(source); },
    label + " no se puede analizar como JavaScript");
}

files.forEach(function (name) {
  var source = fs.readFileSync(path.join(frontend, name), "utf8");
  if (/\.js$/.test(name)) {
    checkES5(name, source);
  } else {
    scriptsFromHtml(source).forEach(function (script, index) {
      checkES5(name + " inline #" + (index + 1), script);
    });
  }
});

console.log("frontend compatibility tests: OK (" + files.length + " files)");

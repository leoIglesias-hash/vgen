/* reader-factory.js - despacho ASCL v1/v2 sin cambiar el contrato de render. */
(function (root) {
  "use strict";

  var legacy = root.ASCL || null;
  var regional = root.ASCLV2 || null;
  if (typeof require === "function") {
    if (!legacy) legacy = require("./reader.js");
    if (!regional) regional = require("./reader-v2.js");
  }

  function fail(message) { throw new Error("ASCL reader: " + message); }

  function parse(buffer, byteOffset, byteLength) {
    var offset, length, view, version;
    if (!buffer || typeof buffer.byteLength !== "number") fail("ArrayBuffer invalido");
    offset = byteOffset === undefined ? 0 : Number(byteOffset);
    length = byteLength === undefined ? buffer.byteLength - offset : Number(byteLength);
    if (offset !== Math.floor(offset) || length !== Math.floor(length) ||
        offset < 0 || length < 5 || offset + length > buffer.byteLength) {
      fail("rango ASCL invalido");
    }
    view = new DataView(buffer, offset, length);
    if (view.getUint8(0) !== 65 || view.getUint8(1) !== 83 ||
        view.getUint8(2) !== 67 || view.getUint8(3) !== 76) fail("magic invalido");
    version = view.getUint8(4);
    if (version === 1) {
      if (!legacy || typeof legacy.parse !== "function") fail("ReaderV1 no disponible");
      return legacy.parse(buffer, offset, length);
    }
    if (version === 2) {
      if (!regional || typeof regional.parse !== "function") fail("ReaderV2 no disponible");
      return regional.parse(buffer, offset, length);
    }
    fail("version no soportada " + version);
  }

  root.ASCILINEReader = { parse: parse };
  if (typeof module !== "undefined" && module.exports) module.exports = root.ASCILINEReader;
})(typeof window !== "undefined" ? window : this);

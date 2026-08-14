#!/usr/bin/env node
"use strict";

/* Verifica dos ASCL/ASCLV mediante los readers reales y compara RGBA por frame. */
var fs = require("fs");
var path = require("path");
var factory = require(path.join(__dirname, "..", "frontend", "reader-factory.js"));

function fail(message) { throw new Error(message); }

function input(filePath) {
  var file = fs.readFileSync(filePath), videoOffset = 0, videoLength = file.length;
  var audio = Buffer.alloc(0), magic, declaredAudio, total;
  if (file.length >= 16 && file.subarray(0, 7).toString("ascii") === "ASCLVID") {
    magic = file.subarray(0, 8).toString("ascii");
    if (magic !== "ASCLVID1" && magic !== "ASCLVID2") fail("bundle desconocido " + magic);
    videoLength = file.readUInt32LE(8);
    declaredAudio = file.readUInt32LE(12);
    total = 16 + videoLength + declaredAudio;
    if (videoLength < 32 || total !== file.length) fail("bundle truncado o con bytes extra");
    videoOffset = 16;
    if (file[videoOffset + 4] !== Number(magic.charAt(7))) fail("version envelope/interior desigual");
    audio = file.subarray(videoOffset + videoLength, total);
  }
  return {
    file: file,
    reader: factory.parse(file.buffer, file.byteOffset + videoOffset, videoLength),
    audio: audio,
    videoLength: videoLength
  };
}

function equalBytes(a, b) {
  var i;
  if (a.length !== b.length) return false;
  for (i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function main(argv) {
  if (argv.length !== 2) {
    process.stderr.write("uso: node backend/verify_v1_v2.js base.ascl[v] candidato.ascl[v]\n");
    return 2;
  }
  var base = input(argv[0]), candidate = input(argv[1]);
  var a = base.reader, b = candidate.reader, i, started = Date.now();
  if (a.header.cols !== b.header.cols || a.header.rows !== b.header.rows ||
      a.header.fps !== b.header.fps || a.header.nFrames !== b.header.nFrames) {
    fail("geometria, FPS o cantidad de frames diferente");
  }
  if (!equalBytes(base.audio, candidate.audio)) fail("audio diferente");
  var rgbaA = new Uint8Array(a.header.cols * a.header.rows * 4);
  var rgbaB = new Uint8Array(rgbaA.length);
  for (i = 0; i < a.header.nFrames; i++) {
    a.seek(i); b.seek(i);
    a.fillRGBA(rgbaA); b.fillRGBA(rgbaB);
    if (!equalBytes(rgbaA, rgbaB)) fail("RGBA diferente en frame " + i);
  }
  process.stdout.write("OK: " + a.header.nFrames + " frames RGBA identicos; audio " +
    base.audio.length + " B identico; video " + base.videoLength + " -> " +
    candidate.videoLength + " B; " + (Date.now() - started) + " ms\n");
  return 0;
}

module.exports = { input: input, equalBytes: equalBytes, main: main };
if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    process.stderr.write("ERROR: " + (error && error.message ? error.message : error) + "\n");
    process.exitCode = 1;
  }
}

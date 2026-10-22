// Regression check for synchronous alert / confirm / prompt semantics.
// The workaround runs in every same-origin frame, then sends a delayed
// recovery signal. Run via node desktop/test_dialog_focus.js (no GUI needed).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "main.js"), "utf8");
const match = source.match(/const NIKA_NATIVE_DIALOG_FOCUS_GUARD = String\.raw\`([\s\S]*?)\`;/);
assert.ok(match, "Native dialog focus guard is embedded in the Electron main process");

function executeGuard(env) {
    const callbacks = [];
    const results = [];
    const host = { recoverKeyboardFocus: () => results.push("recovered") };
    const win = {
        top: { nikaDesktop: host },
        alert: (message) => { results.push(["alert", message]); return undefined; },
        confirm: (message) => { results.push(["confirm", message]); return message === "ok"; },
        prompt: (message, initial) => { results.push(["prompt", message, initial]); return "typed"; },
        setTimeout: (callback) => { callbacks.push(callback); }
    };
    vm.runInNewContext(match[1], {window: win});
    vm.runInNewContext(match[1], {window: win}); // must not wrap twice
    assert.equal(win.confirm("ok"), true);
    assert.equal(win.confirm("cancel"), false);
    assert.equal(win.prompt("enter", "x"), "typed");
    assert.equal(win.alert("notice"), undefined);
    assert.deepEqual(results, [
        ["confirm", "ok"], ["confirm", "cancel"], ["prompt", "enter", "x"], ["alert", "notice"]
    ]);
    assert.equal(callbacks.length, 4, "Only one scheduled repair per dialog");
    callbacks.forEach(f => f());
    assert.equal(results.filter(x => x === "recovered").length, 4);
}
executeGuard();
assert.match(source, /did-frame-finish-load/, "Nested frames must receive the workaround");
assert.match(source, /win\.blur\(\);\s*win\.focus\(\);/, "Restore native IME focus");
assert.match(fs.readFileSync(path.join(__dirname, "preload.js"), "utf8"),
    /recoverKeyboardFocus:\s*\(\)\s*=>\s*ipcRenderer\.send/);
console.log("Electron native dialog focus regression checks passed");

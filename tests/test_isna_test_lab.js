/* Offline smoke test for the ISNA TEST-only signature lab.
 * Tests that signing does NOT invoke the network and that diagnostics use GET only.
 * Run: node tests/test_isna_test_lab.js
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function button() {
  return {
    disabled: false,
    handlers: {},
    addEventListener(event, callback) { this.handlers[event] = callback; },
    async fire(event = 'click') { return this.handlers[event](); }
  };
}

(async () => {
  const elems = {
    isnaTestLab: {},
    isnaTestCheck: button(),
    isnaTestSign: button(),
    isnaTestDownload: button(),
    isnaTestPasswordLabel: { hidden: true },
    isnaTestP12Password: { value: '' },
    isnaTestStatus: { textContent: '' }
  };
  let networkCalls = 0;
  let signedInput = '';
  const context = {
    document: {
      getElementById(name) { return elems[name] || null; },
      createElement() { return { click() {}, remove() {} }; },
      body: { appendChild() {} }
    },
    window: {
      NikaNCALayer: {
        async signXml(xml) {
          signedInput = xml;
          return { signedXml: '<NikaIsnaTest><ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:Signature></NikaIsnaTest>' };
        }
      },
      crypto: { randomUUID() { return 'testing-uuid'; } },
      setTimeout: setTimeout
    },
    crypto: { randomUUID() { return 'testing-uuid'; } },
    fetch: async (url, options) => {
      networkCalls++;
      assert.equal(url, '/accounting/isna/test/diagnostics');
      assert.equal(options.method, 'GET');
      return { ok: true, async json() {
        return { endpoint: 'test-endpoint', tcpOk: false, tcpMessage: 'not available',
          senderConfigured: false, serviceIdConfigured: false, transportSignerConfigured: false,
          note: 'TEST VPS only' };
      }};
    },
    Blob,
    URL,
    Math,
    Date
  };
  const script = fs.readFileSync('static/js/isna_test_lab.js', 'utf8');
  vm.runInNewContext(script, context, { filename: 'isna_test_lab.js' });
  await elems.isnaTestSign.fire();
  assert.equal(networkCalls, 0, 'Signing must not send any data to a server');
  assert.match(signedInput, /Local XML signature compatibility check only/);
  assert.doesNotMatch(signedInput, /taxpayer|declaration|form910/i);
  assert.equal(elems.isnaTestDownload.disabled, false);
  assert.match(elems.isnaTestStatus.textContent, /не отправлен/);
  await elems.isnaTestCheck.fire();
  assert.equal(networkCalls, 1);
  assert.match(elems.isnaTestStatus.textContent, /TEST VPS/);
  console.log('OK: ISNA offline signing / read-only diagnostics');
})().catch(error => { console.error(error); process.exitCode = 1; });

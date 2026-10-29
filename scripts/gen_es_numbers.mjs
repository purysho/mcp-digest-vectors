// Writes python/tests/data/es-numbers.json: [[ieee754 bits as hex, String(x)], ...]
// String(x) is the ECMAScript Number-to-String algorithm that RFC 8785 adopts,
// so both implementations can check their number formatting without Node at test time.
//   node scripts/gen_es_numbers.mjs
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

let s = 0x2545f4914f6cdd1dn; // xorshift64* with a fixed seed: deterministic output
const next = () => {
  s ^= s >> 12n; s ^= (s << 25n) & 0xffffffffffffffffn; s ^= s >> 27n;
  return (s * 0x2545f4914f6cdd1dn) & 0xffffffffffffffffn;
};
const view = new DataView(new ArrayBuffer(8));
const bitsOf = (x) => { view.setFloat64(0, x); return view.getBigUint64(0).toString(16).padStart(16, "0"); };

const out = [];
const push = (x) => { if (Number.isFinite(x)) out.push([bitsOf(x), String(x)]); };

for (let i = 0; i < 3000; i++) { view.setBigUint64(0, next()); push(view.getFloat64(0)); }          // any bit pattern
for (let i = 0; i < 1000; i++) push(Number(next() % 2000000n) / 1000 - 1000);                        // short decimals
for (let i = 0; i < 1000; i++) push(Number(next() % (2n ** 60n)) * (next() % 2n ? 1 : -1));          // large integers
for (let e = -330; e <= 310; e++) { push(Number(`1e${e}`)); push(Number(`7.25e${e}`)); }             // every exponent
[0, -0, 5e-324, -5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 9007199254740991, 9007199254740992,
 1e21, 1e-7, 0.000001, 123456789012345680000, 0.1, 0.2, 0.30000000000000004].forEach(push);

const path = fileURLToPath(new URL("../python/tests/data/es-numbers.json", import.meta.url));
writeFileSync(path, JSON.stringify(out) + "\n");
console.log(`wrote ${out.length} numbers to ${path}`);

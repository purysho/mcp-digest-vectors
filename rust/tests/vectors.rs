//! Re-derive every known answer in ../vectors with this implementation, and check
//! number formatting against values printed by Node.js (ECMAScript itself).

use std::fs;
use std::path::PathBuf;

use base64::Engine;
use mcp_digest::{digest_result, json, Profile};
use serde_json::Value as J;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}

fn side(v: &J, side: &str) -> Vec<u8> {
    if let Some(b) = v.get(format!("{side}_b64")) {
        base64::engine::general_purpose::STANDARD
            .decode(b.as_str().unwrap())
            .unwrap()
    } else {
        v[side].as_str().unwrap().as_bytes().to_vec()
    }
}

#[test]
fn all_vectors_match_known_answers() {
    let mut checked = 0;
    let mut failures = Vec::new();
    let mut paths: Vec<_> = fs::read_dir(root().join("vectors"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|e| e == "json") && !p.ends_with("index.json"))
        .collect();
    paths.sort();
    assert!(
        paths.len() >= 40,
        "expected the vector set, found {}",
        paths.len()
    );
    for path in paths {
        let v: J = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        let id = v["id"].as_str().unwrap();
        for profile in Profile::ALL {
            for s in ["before", "after"] {
                let want = &v["known_answers"][profile.name()][s];
                let got = digest_result(&side(&v, s), profile);
                let ok = match (&got, want.get("reject")) {
                    (Err(_), Some(_)) => true,
                    (Ok(d), None) => {
                        let tools: serde_json::Map<String, J> = d
                            .tool_digests
                            .iter()
                            .map(|(k, v)| (k.clone(), J::String(v.clone())))
                            .collect();
                        want["set"] == J::String(d.set_digest.clone())
                            && want["tools"] == J::Object(tools)
                    }
                    _ => false,
                };
                if !ok {
                    failures.push(format!(
                        "{id} [{}/{s}]: got {:?}",
                        profile.name(),
                        got.map(|d| d.set_digest)
                    ));
                }
                checked += 1;
            }
        }
    }
    assert!(
        failures.is_empty(),
        "{} failures:\n{}",
        failures.len(),
        failures.join("\n")
    );
    println!("checked {checked} vector sides");
}

#[test]
fn reject_codes_match_python_reference() {
    // The Python reference records its reject code in known_answers; codes are
    // informative per SPEC.md, but agreeing on them is a useful cross-check.
    for entry in fs::read_dir(root().join("vectors")).unwrap() {
        let path = entry.unwrap().path();
        if path.ends_with("index.json") {
            continue;
        }
        let v: J = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        for s in ["before", "after"] {
            if let Some(code) = v["known_answers"]["full"][s].get("reject") {
                let got = digest_result(&side(&v, s), Profile::Full).unwrap_err();
                assert_eq!(got.code(), code.as_str().unwrap(), "{}", v["id"]);
            }
        }
    }
}

#[test]
fn numbers_match_ecmascript() {
    let path = root().join("python/tests/data/es-numbers.json");
    let pairs: Vec<(String, String)> =
        serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    assert!(pairs.len() > 1000);
    for (bits, expected) in pairs {
        let x = f64::from_bits(u64::from_str_radix(&bits, 16).unwrap());
        assert_eq!(json::number_to_string(x), expected, "bits {bits}");
    }
}

#[test]
fn rfc8785_testdata() {
    let dir = root().join("python/tests/data/rfc8785");
    for entry in fs::read_dir(dir.join("input")).unwrap() {
        let path = entry.unwrap().path();
        let name = path.file_name().unwrap();
        let v = json::parse(&fs::read(&path).unwrap()).unwrap();
        let expected = fs::read(dir.join("output").join(name)).unwrap();
        assert_eq!(
            json::canonicalize(&v).as_bytes(),
            expected.as_slice(),
            "{name:?}"
        );
    }
}

#[test]
fn strict_parsing() {
    use mcp_digest::Reject::*;
    let cases: &[(&[u8], mcp_digest::Reject)] = &[
        (br#"{"a":1,"a":2}"#, DuplicateKey),
        (br#"{"a":1,"a":2}"#, DuplicateKey),
        (br#"["\ud800"]"#, LoneSurrogate),
        (br#"["\udc00\ud800"]"#, LoneSurrogate),
        (b"[NaN]", InvalidJson),
        (b"[1e400]", NumberOutOfRange),
        (b"[\"\xff\"]", InvalidUtf8),
        (b"\xef\xbb\xbf[]", InvalidJson),
        (b"[1,]", InvalidJson),
        (b"[01]", InvalidJson),
        (b"[1.]", InvalidJson),
        (b"[\"a\tb\"]", InvalidJson),
    ];
    for (raw, want) in cases {
        assert_eq!(
            json::parse(raw).unwrap_err(),
            *want,
            "{:?}",
            String::from_utf8_lossy(raw)
        );
    }
}

//! Independent implementation of `mcp-tool-digest/v1-draft` (see ../SPEC.md).
//!
//! ```
//! let raw = br#"{"tools":[{"name":"echo","description":"Echo text."}]}"#;
//! let d = mcp_digest::digest_result(raw, mcp_digest::Profile::Full).unwrap();
//! assert!(d.set_digest.starts_with("sha256:"));
//! ```

pub mod json;

use std::collections::{BTreeMap, HashSet};
use std::fmt;

use sha2::{Digest, Sha256};

use json::{canonicalize, parse, Value};

pub const VERSION: &str = "mcp-tool-digest/v1-draft";

/// Reasons an input must be rejected (SPEC.md section 2).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reject {
    InvalidUtf8,
    InvalidJson,
    DuplicateKey,
    LoneSurrogate,
    NumberOutOfRange,
    NotAToolList,
    BadToolName,
    DuplicateToolName,
}

impl Reject {
    pub fn code(self) -> &'static str {
        match self {
            Reject::InvalidUtf8 => "invalid-utf8",
            Reject::InvalidJson => "invalid-json",
            Reject::DuplicateKey => "duplicate-key",
            Reject::LoneSurrogate => "lone-surrogate",
            Reject::NumberOutOfRange => "number-out-of-range",
            Reject::NotAToolList => "not-a-tool-list",
            Reject::BadToolName => "bad-tool-name",
            Reject::DuplicateToolName => "duplicate-tool-name",
        }
    }
}

impl fmt::Display for Reject {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.code())
    }
}

impl std::error::Error for Reject {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Profile {
    Desc,
    FourField,
    Full,
}

impl Profile {
    pub const ALL: [Profile; 3] = [Profile::Desc, Profile::FourField, Profile::Full];

    pub fn name(self) -> &'static str {
        match self {
            Profile::Desc => "desc",
            Profile::FourField => "four-field",
            Profile::Full => "full",
        }
    }

    fn fields(self) -> Option<&'static [&'static str]> {
        match self {
            Profile::Desc => Some(&["name", "description"]),
            Profile::FourField => Some(&["name", "description", "inputSchema", "annotations"]),
            Profile::Full => None,
        }
    }

    fn select(self, tool: &[(String, Value)]) -> Value {
        match self.fields() {
            None => Value::Obj(tool.to_vec()),
            Some(fields) => Value::Obj(
                tool.iter()
                    .filter(|(k, _)| fields.contains(&k.as_str()))
                    .cloned()
                    .collect(),
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ListDigest {
    pub set_digest: String,
    /// Tool name -> per-tool digest.
    pub tool_digests: BTreeMap<String, String>,
    /// RFC 8785 text covered by `set_digest` (without the domain prefix).
    pub canonical: String,
}

fn hash(profile: Profile, kind: &str, canonical: &str) -> String {
    let mut h = Sha256::new();
    h.update(format!("{VERSION}/{}/{kind}", profile.name()).as_bytes());
    h.update([0u8]);
    h.update(canonical.as_bytes());
    let out = h.finalize();
    let mut s = String::from("sha256:");
    for b in out {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

/// Digest the raw bytes of a `tools/list` result.
pub fn digest_result(raw: &[u8], profile: Profile) -> Result<ListDigest, Reject> {
    let root = parse(raw)?;
    let tools = match root.get("tools") {
        Some(Value::Arr(items)) if matches!(root, Value::Obj(_)) => items,
        _ => return Err(Reject::NotAToolList),
    };
    let mut named: Vec<(&str, &[(String, Value)])> = Vec::with_capacity(tools.len());
    let mut seen = HashSet::new();
    for t in tools {
        let members = match t {
            Value::Obj(m) => m.as_slice(),
            _ => return Err(Reject::NotAToolList),
        };
        let name = match t.get("name") {
            Some(Value::Str(s)) if !s.is_empty() => s.as_str(),
            _ => return Err(Reject::BadToolName),
        };
        if !seen.insert(name) {
            return Err(Reject::DuplicateToolName);
        }
        named.push((name, members));
    }
    named.sort_by(|a, b| a.0.encode_utf16().cmp(b.0.encode_utf16()));

    let mut tool_digests = BTreeMap::new();
    let mut selected = Vec::with_capacity(named.len());
    for (name, members) in named {
        let s = profile.select(members);
        tool_digests.insert(name.to_string(), hash(profile, "tool", &canonicalize(&s)));
        selected.push(s);
    }
    let canonical = canonicalize(&Value::Arr(selected));
    Ok(ListDigest {
        set_digest: hash(profile, "set", &canonical),
        tool_digests,
        canonical,
    })
}

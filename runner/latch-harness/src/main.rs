//! latch-harness <vector.json>
//!
//! Feeds one vector through Latch's own decision path and prints
//! {"result": "unchanged" | "changed" | "error", "detail": "..."}.
//!
//! Parsing mirrors latch-mcp's stdio transport (stdio.rs): the whole JSON-RPC
//! line is read with `serde_json::from_slice::<Value>`, then each element of
//! `result.tools` becomes a `ToolDescriptor` via `serde_json::from_value`.
//! The snapshot is then reconciled with `ToolRegistry::reconcile`, first for
//! "before" (the pin) and then for "after" (the check).
//!
//! Exit status 3 means the harness could not pin "before" (not a verdict on Latch).

use base64::Engine;
use latch_audit::AuditLedger;
use latch_mcp::{DiscoverySnapshot, ProviderIdentity, ToolDescriptor, ToolRegistry, MCP_PROTOCOL_REVISION};
use serde_json::{json, Value};

fn side(v: &Value, side: &str) -> Vec<u8> {
    if let Some(b) = v.get(format!("{side}_b64")).and_then(Value::as_str) {
        base64::engine::general_purpose::STANDARD.decode(b).expect("valid base64")
    } else {
        v[side].as_str().expect("side text").as_bytes().to_vec()
    }
}

/// What latch-mcp's stdio transport would build from this tools/list response.
fn snapshot(raw_result: &[u8]) -> Result<DiscoverySnapshot, String> {
    let mut line = br#"{"jsonrpc":"2.0","id":2,"result":"#.to_vec();
    line.extend_from_slice(raw_result);
    line.push(b'}');
    let message: Value = serde_json::from_slice(&line).map_err(|e| format!("invalid JSON on MCP stdout: {e}"))?;
    let page = message.get("result").ok_or("no result")?;
    let page_tools = page.get("tools").and_then(Value::as_array).ok_or("tools/list omitted tools array")?;
    let mut tools = Vec::new();
    for tool in page_tools {
        let d: ToolDescriptor = serde_json::from_value(tool.clone()).map_err(|e| format!("descriptor: {e}"))?;
        tools.push(d);
    }
    Ok(DiscoverySnapshot { protocol_revision: MCP_PROTOCOL_REVISION.into(), reported_server: None, tools })
}

fn emit(result: &str, detail: String) {
    println!("{}", json!({"result": result, "detail": detail}));
}

fn main() {
    let path = std::env::args().nth(1).expect("usage: latch-harness <vector.json>");
    let vector: Value = serde_json::from_str(&std::fs::read_to_string(path).expect("read vector")).expect("vector JSON");

    let provider = ProviderIdentity::new("fixture", "stdio", "fixture", &json!({})).expect("provider");
    let mut registry = ToolRegistry::in_memory().expect("registry");
    let mut ledger = AuditLedger::in_memory().expect("ledger");
    registry.register_provider(&provider, 1_000).expect("register provider");

    let before = match snapshot(&side(&vector, "before")) {
        Ok(s) => s,
        Err(e) => {
            emit("harness-error", format!("before: {e}"));
            std::process::exit(3);
        }
    };
    if let Err(e) = registry.reconcile(&provider, &before, &mut ledger, 1_100) {
        emit("harness-error", format!("before reconcile: {e}"));
        std::process::exit(3);
    }

    let after = match snapshot(&side(&vector, "after")) {
        Ok(s) => s,
        Err(e) => return emit("error", e),
    };
    match registry.reconcile(&provider, &after, &mut ledger, 1_200) {
        Err(e) => emit("error", format!("reconcile: {e}")),
        Ok(r) => {
            let mut detail = format!("added={} changed={} missing={} unchanged={}", r.added, r.changed, r.missing, r.unchanged);
            // For tools that first appear after the pin, record whether the registry treats them as active.
            let pinned: Vec<&str> = before.tools.iter().map(|t| t.name.as_str()).collect();
            for t in after.tools.iter().filter(|t| !pinned.contains(&t.name.as_str())) {
                let usable = registry.active_tool(&provider, &t.name).is_ok();
                detail.push_str(&format!("; new tool '{}' active_tool={}", t.name, if usable { "Ok" } else { "Err" }));
            }
            if r.added + r.changed + r.missing > 0 {
                emit("changed", detail)
            } else {
                emit("unchanged", detail)
            }
        }
    }
}

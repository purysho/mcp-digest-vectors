//! Strict JSON parser and RFC 8785 serializer, written from scratch so that this
//! implementation shares no parsing code with the Python reference.

use std::collections::HashSet;
use std::fmt::Write as _;

use crate::Reject;

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Value>),
    /// Members in input order; duplicates are rejected while parsing.
    Obj(Vec<(String, Value)>),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Obj(m) => m.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
}

const MAX_DEPTH: usize = 512;

pub fn parse(bytes: &[u8]) -> Result<Value, Reject> {
    let text = std::str::from_utf8(bytes).map_err(|_| Reject::InvalidUtf8)?;
    let mut p = Parser {
        s: text.as_bytes(),
        i: 0,
        depth: 0,
    };
    p.ws();
    let v = p.value()?;
    p.ws();
    if p.i != p.s.len() {
        return Err(Reject::InvalidJson);
    }
    Ok(v)
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
    depth: usize,
}

impl<'a> Parser<'a> {
    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }

    fn ws(&mut self) {
        while let Some(b' ' | b'\t' | b'\n' | b'\r') = self.peek() {
            self.i += 1;
        }
    }

    fn eat(&mut self, lit: &[u8]) -> Result<(), Reject> {
        if self.s[self.i..].starts_with(lit) {
            self.i += lit.len();
            Ok(())
        } else {
            Err(Reject::InvalidJson)
        }
    }

    fn value(&mut self) -> Result<Value, Reject> {
        match self.peek().ok_or(Reject::InvalidJson)? {
            b'{' => self.object(),
            b'[' => self.array(),
            b'"' => Ok(Value::Str(self.string()?)),
            b't' => self.eat(b"true").map(|_| Value::Bool(true)),
            b'f' => self.eat(b"false").map(|_| Value::Bool(false)),
            b'n' => self.eat(b"null").map(|_| Value::Null),
            b'-' | b'0'..=b'9' => self.number(),
            _ => Err(Reject::InvalidJson),
        }
    }

    fn enter(&mut self) -> Result<(), Reject> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            Err(Reject::InvalidJson)
        } else {
            Ok(())
        }
    }

    fn object(&mut self) -> Result<Value, Reject> {
        self.enter()?;
        self.i += 1;
        let mut members = Vec::new();
        let mut seen = HashSet::new();
        self.ws();
        if self.peek() == Some(b'}') {
            self.i += 1;
            self.depth -= 1;
            return Ok(Value::Obj(members));
        }
        loop {
            self.ws();
            if self.peek() != Some(b'"') {
                return Err(Reject::InvalidJson);
            }
            let key = self.string()?;
            if !seen.insert(key.clone()) {
                return Err(Reject::DuplicateKey);
            }
            self.ws();
            self.eat(b":")?;
            self.ws();
            let v = self.value()?;
            members.push((key, v));
            self.ws();
            match self.peek() {
                Some(b',') => self.i += 1,
                Some(b'}') => {
                    self.i += 1;
                    break;
                }
                _ => return Err(Reject::InvalidJson),
            }
        }
        self.depth -= 1;
        Ok(Value::Obj(members))
    }

    fn array(&mut self) -> Result<Value, Reject> {
        self.enter()?;
        self.i += 1;
        let mut items = Vec::new();
        self.ws();
        if self.peek() == Some(b']') {
            self.i += 1;
            self.depth -= 1;
            return Ok(Value::Arr(items));
        }
        loop {
            self.ws();
            items.push(self.value()?);
            self.ws();
            match self.peek() {
                Some(b',') => self.i += 1,
                Some(b']') => {
                    self.i += 1;
                    break;
                }
                _ => return Err(Reject::InvalidJson),
            }
        }
        self.depth -= 1;
        Ok(Value::Arr(items))
    }

    fn hex4(&mut self) -> Result<u16, Reject> {
        let h = self.s.get(self.i..self.i + 4).ok_or(Reject::InvalidJson)?;
        let h = std::str::from_utf8(h).map_err(|_| Reject::InvalidJson)?;
        if !h.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(Reject::InvalidJson);
        }
        self.i += 4;
        u16::from_str_radix(h, 16).map_err(|_| Reject::InvalidJson)
    }

    fn string(&mut self) -> Result<String, Reject> {
        self.i += 1; // opening quote
        let mut out = String::new();
        loop {
            let b = self.peek().ok_or(Reject::InvalidJson)?;
            match b {
                b'"' => {
                    self.i += 1;
                    return Ok(out);
                }
                b'\\' => {
                    self.i += 1;
                    let e = self.peek().ok_or(Reject::InvalidJson)?;
                    self.i += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let u = self.hex4()?;
                            if (0xD800..0xDC00).contains(&u) {
                                // A high surrogate must be followed by an escaped low surrogate.
                                if self.s[self.i..].starts_with(b"\\u") {
                                    self.i += 2;
                                    let lo = self.hex4()?;
                                    if !(0xDC00..0xE000).contains(&lo) {
                                        return Err(Reject::LoneSurrogate);
                                    }
                                    let cp = 0x10000
                                        + (((u as u32) - 0xD800) << 10)
                                        + ((lo as u32) - 0xDC00);
                                    out.push(char::from_u32(cp).ok_or(Reject::LoneSurrogate)?);
                                } else {
                                    return Err(Reject::LoneSurrogate);
                                }
                            } else if (0xDC00..0xE000).contains(&u) {
                                return Err(Reject::LoneSurrogate);
                            } else {
                                out.push(char::from_u32(u as u32).ok_or(Reject::InvalidJson)?);
                            }
                        }
                        _ => return Err(Reject::InvalidJson),
                    }
                }
                0x00..=0x1F => return Err(Reject::InvalidJson),
                _ => {
                    // Copy one UTF-8 encoded character (input is already valid UTF-8).
                    let len = match b {
                        0x00..=0x7F => 1,
                        0xC0..=0xDF => 2,
                        0xE0..=0xEF => 3,
                        _ => 4,
                    };
                    let chunk = std::str::from_utf8(&self.s[self.i..self.i + len])
                        .map_err(|_| Reject::InvalidUtf8)?;
                    out.push_str(chunk);
                    self.i += len;
                }
            }
        }
    }

    fn digits(&mut self) -> usize {
        let start = self.i;
        while let Some(b'0'..=b'9') = self.peek() {
            self.i += 1;
        }
        self.i - start
    }

    fn number(&mut self) -> Result<Value, Reject> {
        let start = self.i;
        if self.peek() == Some(b'-') {
            self.i += 1;
        }
        match self.peek() {
            Some(b'0') => self.i += 1,
            Some(b'1'..=b'9') => {
                self.digits();
            }
            _ => return Err(Reject::InvalidJson),
        }
        if self.peek() == Some(b'.') {
            self.i += 1;
            if self.digits() == 0 {
                return Err(Reject::InvalidJson);
            }
        }
        if let Some(b'e' | b'E') = self.peek() {
            self.i += 1;
            if let Some(b'+' | b'-') = self.peek() {
                self.i += 1;
            }
            if self.digits() == 0 {
                return Err(Reject::InvalidJson);
            }
        }
        let text = std::str::from_utf8(&self.s[start..self.i]).map_err(|_| Reject::InvalidJson)?;
        let x: f64 = text.parse().map_err(|_| Reject::InvalidJson)?;
        if !x.is_finite() {
            return Err(Reject::NumberOutOfRange);
        }
        Ok(Value::Num(x))
    }
}

// ------------------------------------------------------------------ RFC 8785 serialization

pub fn canonicalize(v: &Value) -> String {
    let mut out = String::new();
    write_value(v, &mut out);
    out
}

fn write_value(v: &Value, out: &mut String) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Num(x) => out.push_str(&number_to_string(*x)),
        Value::Str(s) => write_string(s, out),
        Value::Arr(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_value(item, out);
            }
            out.push(']');
        }
        Value::Obj(members) => {
            let mut sorted: Vec<&(String, Value)> = members.iter().collect();
            sorted.sort_by(|a, b| a.0.encode_utf16().cmp(b.0.encode_utf16()));
            out.push('{');
            for (i, (k, val)) in sorted.into_iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(k, out);
                out.push(':');
                write_value(val, out);
            }
            out.push('}');
        }
    }
}

fn write_string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

/// ECMAScript Number.prototype.toString for a finite f64.
pub fn number_to_string(x: f64) -> String {
    if x == 0.0 {
        return "0".to_string();
    }
    let sign = if x < 0.0 { "-" } else { "" };
    // `{:e}` prints the shortest round-tripping digits, e.g. "1.2345e-7".
    let sci = format!("{:e}", x.abs());
    let (mant, exp) = sci
        .split_once('e')
        .expect("LowerExp always has an exponent");
    let exp: i32 = exp.parse().expect("integer exponent");
    let digits: String = mant.chars().filter(|c| *c != '.').collect();
    let k = digits.len() as i32;
    let n = exp + 1;
    let body = if k <= n && n <= 21 {
        format!("{}{}", digits, "0".repeat((n - k) as usize))
    } else if 0 < n && n <= 21 {
        format!("{}.{}", &digits[..n as usize], &digits[n as usize..])
    } else if -6 < n && n <= 0 {
        format!("0.{}{}", "0".repeat((-n) as usize), digits)
    } else {
        let e = n - 1;
        let m = if k == 1 {
            digits.clone()
        } else {
            format!("{}.{}", &digits[..1], &digits[1..])
        };
        format!("{}e{}{}", m, if e > 0 { "+" } else { "-" }, e.abs())
    };
    format!("{sign}{body}")
}

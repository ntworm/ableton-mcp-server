use std::collections::HashMap;
use std::fs;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;

use subtle::ConstantTimeEq;

const MAX_HEADER_BYTES: usize = 16 * 1024;
const CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

#[derive(Debug)]
pub struct ParsedRequest {
    method: String,
    path: String,
    headers: HashMap<String, String>,
}

impl ParsedRequest {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .get(&name.to_ascii_lowercase())
            .map(String::as_str)
    }
}

pub fn parse_request(raw: &str) -> Result<ParsedRequest, &'static str> {
    let mut lines = raw.split("\r\n");
    let mut first = lines
        .next()
        .ok_or("MISSING_REQUEST_LINE")?
        .split_ascii_whitespace();
    let method = first.next().ok_or("MISSING_METHOD")?.to_owned();
    let path = first.next().ok_or("MISSING_PATH")?.to_owned();
    if first.next() != Some("HTTP/1.1") || first.next().is_some() {
        return Err("INVALID_REQUEST_LINE");
    }
    let mut headers = HashMap::new();
    for line in lines.take_while(|line| !line.is_empty()) {
        let (name, value) = line.split_once(':').ok_or("INVALID_HEADER")?;
        headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_owned());
    }
    Ok(ParsedRequest {
        method,
        path,
        headers,
    })
}

pub fn token_matches(authorization: &str, token: &str) -> bool {
    let expected = format!("Bearer {token}");
    authorization.as_bytes().ct_eq(expected.as_bytes()).into()
}

pub fn asset_name(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        "/" => Some(("index.html", "text/html; charset=utf-8")),
        "/app.js" => Some(("app.js", "text/javascript; charset=utf-8")),
        "/styles.css" => Some(("styles.css", "text/css; charset=utf-8")),
        _ => None,
    }
}

fn write_response(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    body: &[u8],
) -> io::Result<()> {
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nContent-Security-Policy: {CSP}\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    stream.write_all(body)
}

fn read_headers(stream: &mut TcpStream) -> io::Result<String> {
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    let mut data = Vec::with_capacity(1024);
    let mut byte = [0_u8; 1];
    while data.len() < MAX_HEADER_BYTES {
        if stream.read(&mut byte)? == 0 {
            break;
        }
        data.push(byte[0]);
        if data.ends_with(b"\r\n\r\n") {
            return String::from_utf8(data)
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "non-utf8 header"));
        }
    }
    Err(io::Error::new(
        io::ErrorKind::InvalidData,
        "header too large or incomplete",
    ))
}

fn handle_connection(
    mut stream: TcpStream,
    ui_dir: &Path,
    token: &str,
    expected_host: &str,
) -> io::Result<()> {
    let raw = match read_headers(&mut stream) {
        Ok(raw) => raw,
        Err(_) => {
            return write_response(&mut stream, "400 Bad Request", "text/plain", b"bad request");
        }
    };
    let request = match parse_request(&raw) {
        Ok(request) => request,
        Err(_) => {
            return write_response(&mut stream, "400 Bad Request", "text/plain", b"bad request");
        }
    };

    if request.header("host") != Some(expected_host) {
        return write_response(&mut stream, "403 Forbidden", "text/plain", b"forbidden");
    }

    if request.path == "/api/health" {
        let expected_origin = format!("http://{expected_host}");
        if request.method != "POST" || request.header("origin") != Some(expected_origin.as_str()) {
            return write_response(&mut stream, "403 Forbidden", "text/plain", b"forbidden");
        }
        let authorized = request
            .header("authorization")
            .is_some_and(|value| token_matches(value, token));
        if !authorized {
            return write_response(
                &mut stream,
                "401 Unauthorized",
                "application/json",
                br#"{"status":"unauthorized"}"#,
            );
        }
        return write_response(
            &mut stream,
            "200 OK",
            "application/json",
            br#"{"status":"ok","protocol":1}"#,
        );
    }

    if request.method != "GET" {
        return write_response(
            &mut stream,
            "405 Method Not Allowed",
            "text/plain",
            b"method not allowed",
        );
    }
    let Some((name, content_type)) = asset_name(&request.path) else {
        return write_response(&mut stream, "404 Not Found", "text/plain", b"not found");
    };
    let body = fs::read(ui_dir.join(name))?;
    write_response(&mut stream, "200 OK", content_type, &body)
}

pub fn bind_loopback() -> io::Result<TcpListener> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

pub fn run(
    listener: TcpListener,
    ui_dir: PathBuf,
    token: String,
    shutdown: Arc<AtomicBool>,
) -> io::Result<()> {
    let port = listener.local_addr()?.port();
    let expected_host = format!("localhost:{port}");

    while !shutdown.load(Ordering::Acquire) {
        match listener.accept() {
            Ok((stream, address)) if address.ip().is_loopback() => {
                let _ = handle_connection(stream, &ui_dir, &token, &expected_host);
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(20));
            }
            Err(error) => return Err(error),
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_exact_local_request() {
        let request = parse_request("POST /api/health HTTP/1.1\r\nHost: localhost:45123\r\nOrigin: http://localhost:45123\r\nAuthorization: Bearer aaaa\r\nContent-Length: 0\r\n\r\n").unwrap();
        assert_eq!(request.method, "POST");
        assert_eq!(request.path, "/api/health");
        assert_eq!(request.header("host"), Some("localhost:45123"));
    }

    #[test]
    fn token_comparison_is_exact() {
        assert!(token_matches("Bearer abc", "abc"));
        assert!(!token_matches("Bearer abcd", "abc"));
        assert!(!token_matches("abc", "abc"));
    }

    #[test]
    fn only_known_assets_resolve() {
        assert_eq!(
            asset_name("/"),
            Some(("index.html", "text/html; charset=utf-8"))
        );
        assert_eq!(
            asset_name("/app.js"),
            Some(("app.js", "text/javascript; charset=utf-8"))
        );
        assert_eq!(asset_name("/../secret"), None);
    }
}

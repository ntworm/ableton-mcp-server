use std::collections::HashMap;
use std::fs;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use subtle::ConstantTimeEq;

use crate::catalog::{Catalog, Query};
use crate::net::is_allowed_peer;
use std::sync::Mutex;

const MAX_HEADER_BYTES: usize = 16 * 1024;
const CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
const CONNECTION_TIMEOUT: Duration = Duration::from_secs(2);
const IO_POLL_INTERVAL: Duration = Duration::from_millis(50);
// A search filter is three short strings. Anything larger is not a filter.
const MAX_BODY_BYTES: usize = 4 * 1024;
/// A picker shows a page, not a corpus. Above this the filter is too broad, and
/// a narrower filter is the answer rather than a longer response.
pub const MAX_SEARCH_RESULTS: usize = 100;

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

pub fn is_api_route(path: &str) -> bool {
    matches!(
        path,
        "/api/health"
            | "/api/panel"
            | "/api/search"
            | "/api/groove"
            | "/api/select"
            | "/api/selection"
    )
}

/// What the browser picked, waiting for the extension to collect it.
///
/// The panel no longer returns the choice through the modal, because the modal
/// closes before the user has picked anything. The browser posts here and the
/// extension polls, which is what lets Live stay usable in between.
#[derive(Default)]
pub struct Selection {
    chosen: Mutex<Option<String>>,
}

impl Selection {
    pub fn set(&self, id: String) {
        // Last write wins: changing your mind on the phone should change what
        // lands in the slot, not queue a second clip.
        *self.chosen.lock().expect("selection mutex") = Some(id);
    }

    pub fn take(&self) -> Option<String> {
        self.chosen.lock().expect("selection mutex").take()
    }
}

#[derive(Debug, serde::Deserialize)]
pub struct SearchBody {
    #[serde(default)]
    pub genre: Option<String>,
    #[serde(default)]
    pub bpm: Option<String>,
    #[serde(default)]
    pub kit: Option<String>,
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    MAX_SEARCH_RESULTS
}

impl SearchBody {
    pub fn query(&self) -> Query {
        Query {
            genre: self.genre.clone(),
            bpm: self.bpm.clone(),
            kit: self.kit.clone(),
        }
    }
}

pub fn parse_search_body(raw: &str) -> Result<SearchBody, &'static str> {
    let mut body: SearchBody = serde_json::from_str(raw).map_err(|_| "INVALID_SEARCH_BODY")?;
    body.limit = body.limit.min(MAX_SEARCH_RESULTS);
    Ok(body)
}

#[derive(Debug, serde::Deserialize)]
pub struct GrooveBody {
    pub id: String,
}

pub fn parse_groove_body(raw: &str) -> Result<GrooveBody, &'static str> {
    serde_json::from_str(raw).map_err(|_| "INVALID_GROOVE_BODY")
}

#[derive(serde::Serialize)]
struct SearchHit<'a> {
    id: &'a str,
    genre: &'a [String],
    bpm: &'a [String],
    kit: &'a [String],
    bars: u32,
    meter: &'a str,
    note_count: usize,
}

/// Search results carry no notes. A filter matching a thousand grooves would
/// otherwise return megabytes to render a list nobody has picked from yet.
pub fn search_response(catalog: &Catalog, body: &SearchBody) -> String {
    let hits = catalog.search(&body.query());
    let total = hits.len();
    let items: Vec<SearchHit> = hits
        .into_iter()
        .take(body.limit)
        .map(|groove| SearchHit {
            id: &groove.id,
            genre: &groove.genre,
            bpm: &groove.bpm,
            kit: &groove.kit,
            bars: groove.bars,
            meter: &groove.meter,
            note_count: groove.notes.len(),
        })
        .collect();
    serde_json::json!({"total": total, "returned": items.len(), "items": items}).to_string()
}

#[derive(Debug, serde::Deserialize)]
pub struct SelectBody {
    pub id: String,
}

pub fn parse_select_body(raw: &str) -> Result<SelectBody, &'static str> {
    serde_json::from_str(raw).map_err(|_| "INVALID_SELECT_BODY")
}

pub fn groove_response(catalog: &Catalog, id: &str) -> Option<String> {
    catalog.groove(id).map(|groove| {
        serde_json::json!({
            "id": groove.id,
            "bars": groove.bars,
            "meter": groove.meter,
            "ppq": groove.ppq,
            "notes": groove.notes,
        })
        .to_string()
    })
}

pub fn token_matches(authorization: &str, token: &str) -> bool {
    let expected = format!("Bearer {token}");
    authorization.as_bytes().ct_eq(expected.as_bytes()).into()
}

/// True when a Host header names this helper's port, whatever address it used.
pub fn host_has_port(host: &str, port: u16) -> bool {
    // Split from the right: an IPv6 literal host is bracketed and full of
    // colons, so the last one is the port separator.
    match host.rsplit_once(':') {
        Some((_address, given)) => given.parse::<u16>() == Ok(port),
        None => false,
    }
}

pub fn asset_name(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        "/" => Some(("index.html", "text/html; charset=utf-8")),
        "/app.js" => Some(("app.js", "text/javascript; charset=utf-8")),
        "/styles.css" => Some(("styles.css", "text/css; charset=utf-8")),
        "/picker.html" => Some(("picker.html", "text/html; charset=utf-8")),
        "/picker.js" => Some(("picker.js", "text/javascript; charset=utf-8")),
        _ => None,
    }
}

fn write_response(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    body: &[u8],
    shutdown: &AtomicBool,
    deadline: Instant,
) -> io::Result<()> {
    let headers = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nContent-Security-Policy: {CSP}\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        body.len()
    );
    write_bounded(stream, headers.as_bytes(), shutdown, deadline)?;
    write_bounded(stream, body, shutdown, deadline)
}

fn next_io_timeout(shutdown: &AtomicBool, deadline: Instant) -> io::Result<Duration> {
    if shutdown.load(Ordering::Acquire) {
        return Err(io::Error::new(
            io::ErrorKind::Interrupted,
            "shutdown requested",
        ));
    }
    let remaining = deadline.saturating_duration_since(Instant::now());
    if remaining.is_zero() {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "connection deadline exceeded",
        ));
    }
    Ok(remaining.min(IO_POLL_INTERVAL))
}

fn is_retryable_io_error(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        io::ErrorKind::Interrupted | io::ErrorKind::WouldBlock
    )
}

fn write_bounded(
    stream: &mut TcpStream,
    mut data: &[u8],
    shutdown: &AtomicBool,
    deadline: Instant,
) -> io::Result<()> {
    while !data.is_empty() {
        let poll_interval = next_io_timeout(shutdown, deadline)?;
        match stream.write(data) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::WriteZero,
                    "failed to write response",
                ));
            }
            Ok(written) => data = &data[written..],
            Err(error) if is_retryable_io_error(&error) => {
                if error.kind() == io::ErrorKind::WouldBlock {
                    thread::sleep(poll_interval);
                }
            }
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

fn read_headers(
    stream: &mut TcpStream,
    shutdown: &AtomicBool,
    deadline: Instant,
) -> io::Result<String> {
    let mut data = Vec::with_capacity(1024);
    let mut byte = [0_u8; 1];
    while data.len() < MAX_HEADER_BYTES {
        let poll_interval = next_io_timeout(shutdown, deadline)?;
        match stream.read(&mut byte) {
            Ok(0) => break,
            Ok(_) => {
                data.push(byte[0]);
                if data.ends_with(b"\r\n\r\n") {
                    return String::from_utf8(data).map_err(|_| {
                        io::Error::new(io::ErrorKind::InvalidData, "non-utf8 header")
                    });
                }
            }
            Err(error) if is_retryable_io_error(&error) => {
                if error.kind() == io::ErrorKind::WouldBlock {
                    thread::sleep(poll_interval);
                }
            }
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::InvalidData,
        "header too large or incomplete",
    ))
}

/// Read exactly Content-Length bytes, under the same deadline and shutdown
/// discipline the headers use. A body shorter than it claims must not hold the
/// connection open until the deadline on a helper that has to shut down fast.
fn read_body(
    stream: &mut TcpStream,
    length: usize,
    shutdown: &AtomicBool,
    deadline: Instant,
) -> io::Result<String> {
    if length > MAX_BODY_BYTES {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "body too large"));
    }
    let mut data = vec![0_u8; 0];
    let mut byte = [0_u8; 1];
    while data.len() < length {
        let poll_interval = next_io_timeout(shutdown, deadline)?;
        match stream.read(&mut byte) {
            Ok(0) => break,
            Ok(_) => data.push(byte[0]),
            Err(error) if is_retryable_io_error(&error) => {
                if error.kind() == io::ErrorKind::WouldBlock {
                    thread::sleep(poll_interval);
                }
            }
            Err(error) => return Err(error),
        }
    }
    if data.len() != length {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "short body"));
    }
    String::from_utf8(data).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "non-utf8 body"))
}

fn handle_connection(
    mut stream: TcpStream,
    ui_dir: &Path,
    token: &str,
    port: u16,
    shutdown: &AtomicBool,
    catalog: &Catalog,
    selection: &Selection,
) -> io::Result<()> {
    let deadline = Instant::now() + CONNECTION_TIMEOUT;
    let raw = match read_headers(&mut stream, shutdown, deadline) {
        Ok(raw) => raw,
        Err(_) => {
            return write_response(
                &mut stream,
                "400 Bad Request",
                "text/plain",
                b"bad request",
                shutdown,
                deadline,
            );
        }
    };
    let request = match parse_request(&raw) {
        Ok(request) => request,
        Err(_) => {
            return write_response(
                &mut stream,
                "400 Bad Request",
                "text/plain",
                b"bad request",
                shutdown,
                deadline,
            );
        }
    };

    // The port is what identifies this helper; the address depends on which
    // interface the client came in on, and both localhost and the LAN address
    // are legitimate. The peer check has already bounded who may ask.
    let host = request.header("host").unwrap_or_default();
    if !host_has_port(host, port) {
        return write_response(
            &mut stream,
            "403 Forbidden",
            "text/plain",
            b"forbidden",
            shutdown,
            deadline,
        );
    }

    if is_api_route(&request.path) {
        // Same-origin, whatever origin the client used to get here: the page
        // that may call these routes is the one this helper served.
        let expected_origin = format!("http://{host}");
        if request.method != "POST" || request.header("origin") != Some(expected_origin.as_str()) {
            return write_response(
                &mut stream,
                "403 Forbidden",
                "text/plain",
                b"forbidden",
                shutdown,
                deadline,
            );
        }
        // Drained before anything is written, including a refusal. Replying and
        // closing with unread bytes still in the socket makes Windows send an
        // RST, and the client sees a reset connection instead of the response.
        let length = request
            .header("content-length")
            .and_then(|value| value.parse::<usize>().ok())
            .unwrap_or(0);
        let raw_body = match read_body(&mut stream, length, shutdown, deadline) {
            Ok(body) if body.is_empty() => "{}".to_owned(),
            Ok(body) => body,
            Err(_) => {
                return write_response(
                    &mut stream,
                    "400 Bad Request",
                    "text/plain",
                    b"bad request",
                    shutdown,
                    deadline,
                );
            }
        };
        let authorized = request
            .header("authorization")
            .is_some_and(|value| token_matches(value, token));
        if !authorized {
            return write_response(
                &mut stream,
                "401 Unauthorized",
                "application/json",
                br#"{"status":"unauthorized"}"#,
                shutdown,
                deadline,
            );
        }

        let payload = if request.path == "/api/health" {
            Ok(r#"{"status":"ok","protocol":1}"#.to_owned())
        } else if request.path == "/api/select" {
            parse_select_body(&raw_body)
                .map_err(|_| "400 Bad Request")
                // Refusing an id the catalog does not hold keeps a typo in the
                // browser from parking a selection the extension waits on.
                .and_then(|body| match catalog.groove(&body.id) {
                    Some(_) => {
                        selection.set(body.id);
                        Ok(r#"{"status":"selected"}"#.to_owned())
                    }
                    None => Err("404 Not Found"),
                })
        } else if request.path == "/api/panel" {
            // The URL and its QR, so the page inside Live can hand the panel
            // over to a phone without knowing the machine's own address.
            let url = crate::net::panel_url(port, token, "picker.html");
            Ok(match crate::qr::svg(&url) {
                Ok(image) => serde_json::json!({"url": url, "qr": image}).to_string(),
                // A URL too long to encode is still a URL someone can type.
                Err(_) => serde_json::json!({"url": url, "qr": null}).to_string(),
            })
        } else if request.path == "/api/selection" {
            // Taken, not read: the extension collects a pick once, and a second
            // poll after a write must not queue the same groove again.
            Ok(match selection.take() {
                Some(id) => serde_json::json!({"id": id}).to_string(),
                None => r#"{"id":null}"#.to_owned(),
            })
        } else if request.path == "/api/search" {
            parse_search_body(&raw_body)
                .map(|body| search_response(catalog, &body))
                .map_err(|_| "400 Bad Request")
        } else {
            parse_groove_body(&raw_body)
                .map_err(|_| "400 Bad Request")
                // An unknown id is 404: the caller asked for one specific
                // groove, and an empty object would read as one with no notes.
                .and_then(|body| groove_response(catalog, &body.id).ok_or("404 Not Found"))
        };

        return match payload {
            Ok(json) => write_response(
                &mut stream,
                "200 OK",
                "application/json",
                json.as_bytes(),
                shutdown,
                deadline,
            ),
            Err(status) => write_response(
                &mut stream,
                status,
                "text/plain",
                status.as_bytes(),
                shutdown,
                deadline,
            ),
        };
    }

    if request.method != "GET" {
        return write_response(
            &mut stream,
            "405 Method Not Allowed",
            "text/plain",
            b"method not allowed",
            shutdown,
            deadline,
        );
    }
    let Some((name, content_type)) = asset_name(&request.path) else {
        return write_response(
            &mut stream,
            "404 Not Found",
            "text/plain",
            b"not found",
            shutdown,
            deadline,
        );
    };
    let body = fs::read(ui_dir.join(name))?;
    write_response(
        &mut stream,
        "200 OK",
        content_type,
        &body,
        shutdown,
        deadline,
    )
}

/// Listen on every interface so a phone on the same Wi-Fi can reach the panel.
///
/// The accept loop refuses any peer that is not on a private network, so this
/// is wider than loopback but not open: what it adds is the LAN, not the
/// internet.
pub fn bind_lan() -> io::Result<TcpListener> {
    let listener = TcpListener::bind("0.0.0.0:0")?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

fn is_transient_accept_error(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        io::ErrorKind::WouldBlock
            | io::ErrorKind::Interrupted
            | io::ErrorKind::ConnectionAborted
            | io::ErrorKind::ConnectionReset
    )
}

pub fn run(
    listener: TcpListener,
    ui_dir: PathBuf,
    token: String,
    shutdown: Arc<AtomicBool>,
    catalog: Arc<Catalog>,
    selection: Arc<Selection>,
) -> io::Result<()> {
    let port = listener.local_addr()?.port();


    while !shutdown.load(Ordering::Acquire) {
        match listener.accept() {
            Ok((stream, address)) if is_allowed_peer(address.ip()) => {
                stream.set_nonblocking(true)?;
                let _ = handle_connection(
                    stream,
                    &ui_dir,
                    &token,
                    port,
                    shutdown.as_ref(),
                    catalog.as_ref(),
                    selection.as_ref(),
                );
            }
            Ok(_) => {}
            Err(error) if is_transient_accept_error(&error) => {
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

    const SAMPLE: &str = r#"{
        "schema": "groove.export.v1",
        "grooves": [
            {"id":"a1","genre":["metal"],"bpm":["bpm_140_159"],"kit":["kick"],
             "bars":4,"meter":"4/4","ppq":480,"notes":[[36,0,120,100]]}
        ]
    }"#;

    #[test]
    fn a_host_is_accepted_by_its_port_whatever_address_it_names() {
        // A phone reaches the helper at the LAN address and the same machine
        // reaches it at localhost. Both are legitimate; the port is what
        // identifies this helper, and the peer check bounds who may ask.
        assert!(host_has_port("localhost:45123", 45123));
        assert!(host_has_port("192.168.1.40:45123", 45123));
        assert!(host_has_port("[fd00::1]:45123", 45123));
        assert!(!host_has_port("localhost:45124", 45123));
        assert!(!host_has_port("localhost", 45123));
        assert!(!host_has_port("", 45123));
    }

    #[test]
    fn a_selection_is_collected_once() {
        // The extension polls until something arrives. Reading without taking
        // would make a second poll after the write queue the same groove again.
        let selection = Selection::default();
        assert_eq!(selection.take(), None);
        selection.set("a1".to_owned());
        assert_eq!(selection.take(), Some("a1".to_owned()));
        assert_eq!(selection.take(), None);
    }

    #[test]
    fn changing_your_mind_replaces_the_pick_rather_than_queueing_one() {
        let selection = Selection::default();
        selection.set("a1".to_owned());
        selection.set("b2".to_owned());
        assert_eq!(selection.take(), Some("b2".to_owned()));
        assert_eq!(selection.take(), None);
    }

    #[test]
    fn a_select_body_needs_an_id() {
        assert_eq!(parse_select_body(r#"{"id":"a1"}"#).unwrap().id, "a1");
        assert!(parse_select_body("{}").is_err());
        assert!(parse_select_body("not json").is_err());
    }

    #[test]
    fn the_picker_pages_are_servable_and_nothing_else_is() {
        assert!(asset_name("/picker.html").is_some());
        assert!(asset_name("/picker.js").is_some());
        assert_eq!(asset_name("/../secret"), None);
        assert_eq!(asset_name("/data/grooves.json"), None);
    }

    #[test]
    fn every_api_route_is_recognised_and_nothing_else_is() {
        assert!(is_api_route("/api/search"));
        assert!(is_api_route("/api/groove"));
        assert!(is_api_route("/api/health"));
        assert!(!is_api_route("/api/../secret"));
        assert!(!is_api_route("/app.js"));
    }

    #[test]
    fn a_search_body_becomes_a_query() {
        let body = parse_search_body(r#"{"genre":"metal","bpm":"bpm_140_159"}"#).unwrap();
        assert_eq!(body.genre.as_deref(), Some("metal"));
        assert_eq!(body.bpm.as_deref(), Some("bpm_140_159"));
        assert_eq!(body.kit, None);
    }

    #[test]
    fn an_empty_body_is_an_empty_query_not_an_error() {
        assert_eq!(parse_search_body("{}").unwrap().genre, None);
    }

    #[test]
    fn a_malformed_search_body_is_refused() {
        assert!(parse_search_body("not json").is_err());
        assert!(parse_search_body(r#"{"genre":42}"#).is_err());
    }

    #[test]
    fn a_requested_limit_cannot_exceed_the_cap() {
        // A query matching everything must not return the whole export as one
        // response; the list is a picker, not a dump.
        assert_eq!(
            parse_search_body(r#"{"limit":9999}"#).unwrap().limit,
            MAX_SEARCH_RESULTS
        );
    }

    #[test]
    fn a_search_response_omits_notes_but_counts_them() {
        let catalog = Catalog::from_str(SAMPLE).unwrap();
        let body = parse_search_body("{}").unwrap();
        let json = search_response(&catalog, &body);
        assert!(json.contains(r#""note_count":1"#));
        assert!(!json.contains(r#""notes""#));
    }

    #[test]
    fn a_groove_response_carries_notes_and_an_unknown_id_carries_nothing() {
        let catalog = Catalog::from_str(SAMPLE).unwrap();
        assert!(groove_response(&catalog, "a1").unwrap().contains("[36,0,120,100]"));
        assert!(groove_response(&catalog, "nope").is_none());
    }

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

    #[test]
    fn serves_request_fragmented_after_accept() {
        let listener = bind_lan().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(
                    listener,
                    PathBuf::new(),
                    "abc".to_owned(),
                    server_shutdown,
                    Arc::new(Catalog::from_str(SAMPLE).unwrap()),
                    Arc::new(Selection::default()),
                ));

        let mut client = TcpStream::connect(("127.0.0.1", port)).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        client
            .set_write_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        thread::sleep(Duration::from_millis(100));
        let first_write = client.write_all(b"POST /api/health HTTP/1.1\r\nHost: local");
        thread::sleep(Duration::from_millis(50));
        let second_write = client.write_all(
            format!(
                "host:{port}\r\nOrigin: http://localhost:{port}\r\nAuthorization: Bearer abc\r\nContent-Length: 0\r\n\r\n"
            )
            .as_bytes(),
        );
        let mut response = Vec::new();
        let read_result = client.read_to_end(&mut response);

        shutdown.store(true, Ordering::Release);
        let server_result = server_thread.join().unwrap();

        first_write.unwrap();
        second_write.unwrap();
        read_result.unwrap();
        server_result.unwrap();
        assert!(response.starts_with(b"HTTP/1.1 200 OK\r\n"));
    }

    #[test]
    fn shutdown_interrupts_partial_request_promptly() {
        let listener = bind_lan().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(
                    listener,
                    PathBuf::new(),
                    "abc".to_owned(),
                    server_shutdown,
                    Arc::new(Catalog::from_str(SAMPLE).unwrap()),
                    Arc::new(Selection::default()),
                ));

        let mut client = TcpStream::connect(("127.0.0.1", port)).unwrap();
        client
            .write_all(b"POST /api/health HTTP/1.1\r\nHost: local")
            .unwrap();
        thread::sleep(Duration::from_millis(200));

        let started = std::time::Instant::now();
        shutdown.store(true, Ordering::Release);
        let limit = Duration::from_secs(1);
        while !server_thread.is_finished() && started.elapsed() < limit {
            thread::sleep(Duration::from_millis(20));
        }
        let stopped_promptly = server_thread.is_finished();

        drop(client);
        server_thread.join().unwrap().unwrap();
        assert!(
            stopped_promptly,
            "server did not stop within {limit:?} while a partial request was stalled"
        );
    }

    #[test]
    fn slow_fragments_cannot_extend_connection_deadline() {
        let listener = bind_lan().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(
                    listener,
                    PathBuf::new(),
                    "abc".to_owned(),
                    server_shutdown,
                    Arc::new(Catalog::from_str(SAMPLE).unwrap()),
                    Arc::new(Selection::default()),
                ));

        let mut client = TcpStream::connect(("127.0.0.1", port)).unwrap();
        client
            .set_read_timeout(Some(Duration::from_millis(250)))
            .unwrap();
        for _ in 0..5 {
            client.write_all(b"x").unwrap();
            thread::sleep(Duration::from_millis(400));
        }
        thread::sleep(Duration::from_millis(300));
        let mut response_byte = [0_u8; 1];
        let read_result = client.read(&mut response_byte);

        shutdown.store(true, Ordering::Release);
        drop(client);
        server_thread.join().unwrap().unwrap();
        assert!(
            matches!(read_result, Ok(0)),
            "expected EOF after total deadline, got {read_result:?}"
        );
    }

    #[test]
    fn classifies_only_expected_accept_errors_as_transient() {
        for kind in [
            io::ErrorKind::WouldBlock,
            io::ErrorKind::Interrupted,
            io::ErrorKind::ConnectionAborted,
            io::ErrorKind::ConnectionReset,
        ] {
            assert!(is_transient_accept_error(&io::Error::from(kind)));
        }
        assert!(!is_transient_accept_error(&io::Error::from(
            io::ErrorKind::AddrNotAvailable,
        )));
        #[cfg(windows)]
        for raw_os_error in [10053, 10054] {
            assert!(is_transient_accept_error(&io::Error::from_raw_os_error(
                raw_os_error,
            )));
        }
    }

    #[test]
    fn retries_only_nonblocking_progress_errors() {
        assert!(is_retryable_io_error(&io::Error::from(
            io::ErrorKind::WouldBlock,
        )));
        assert!(is_retryable_io_error(&io::Error::from(
            io::ErrorKind::Interrupted,
        )));
        assert!(!is_retryable_io_error(&io::Error::from(
            io::ErrorKind::TimedOut,
        )));
        assert!(!is_retryable_io_error(&io::Error::from(
            io::ErrorKind::ConnectionReset,
        )));
    }
}

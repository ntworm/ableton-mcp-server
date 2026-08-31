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

const MAX_HEADER_BYTES: usize = 16 * 1024;
const CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
const CONNECTION_TIMEOUT: Duration = Duration::from_secs(2);
const IO_POLL_INTERVAL: Duration = Duration::from_millis(50);

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

fn write_bounded(
    stream: &mut TcpStream,
    mut data: &[u8],
    shutdown: &AtomicBool,
    deadline: Instant,
) -> io::Result<()> {
    while !data.is_empty() {
        stream.set_write_timeout(Some(next_io_timeout(shutdown, deadline)?))?;
        match stream.write(data) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::WriteZero,
                    "failed to write response",
                ));
            }
            Ok(written) => data = &data[written..],
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::Interrupted
                        | io::ErrorKind::WouldBlock
                        | io::ErrorKind::TimedOut
                ) => {}
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
        stream.set_read_timeout(Some(next_io_timeout(shutdown, deadline)?))?;
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
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::Interrupted
                        | io::ErrorKind::WouldBlock
                        | io::ErrorKind::TimedOut
                ) => {}
            Err(error) => return Err(error),
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
    shutdown: &AtomicBool,
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

    if request.header("host") != Some(expected_host) {
        return write_response(
            &mut stream,
            "403 Forbidden",
            "text/plain",
            b"forbidden",
            shutdown,
            deadline,
        );
    }

    if request.path == "/api/health" {
        let expected_origin = format!("http://{expected_host}");
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
        return write_response(
            &mut stream,
            "200 OK",
            "application/json",
            br#"{"status":"ok","protocol":1}"#,
            shutdown,
            deadline,
        );
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

pub fn bind_loopback() -> io::Result<TcpListener> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
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
) -> io::Result<()> {
    let port = listener.local_addr()?.port();
    let expected_host = format!("localhost:{port}");

    while !shutdown.load(Ordering::Acquire) {
        match listener.accept() {
            Ok((stream, address)) if address.ip().is_loopback() => {
                stream.set_nonblocking(false)?;
                let _ =
                    handle_connection(stream, &ui_dir, &token, &expected_host, shutdown.as_ref());
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
        let listener = bind_loopback().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(listener, PathBuf::new(), "abc".to_owned(), server_shutdown));

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
        let listener = bind_loopback().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(listener, PathBuf::new(), "abc".to_owned(), server_shutdown));

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
        let listener = bind_loopback().unwrap();
        let port = listener.local_addr().unwrap().port();
        let shutdown = Arc::new(AtomicBool::new(false));
        let server_shutdown = Arc::clone(&shutdown);
        let server_thread =
            thread::spawn(move || run(listener, PathBuf::new(), "abc".to_owned(), server_shutdown));

        let mut client = TcpStream::connect(("127.0.0.1", port)).unwrap();
        client
            .set_read_timeout(Some(Duration::from_millis(250)))
            .unwrap();
        let mut connection_closed = false;
        for _ in 0..7 {
            if client.write_all(b"x").is_err() {
                connection_closed = true;
                break;
            }
            thread::sleep(Duration::from_millis(400));
        }
        if !connection_closed {
            let mut response_byte = [0_u8; 1];
            connection_closed = match client.read(&mut response_byte) {
                Ok(_) => true,
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut
                    ) =>
                {
                    false
                }
                Err(_) => true,
            };
        }

        shutdown.store(true, Ordering::Release);
        drop(client);
        server_thread.join().unwrap().unwrap();
        assert!(
            connection_closed,
            "periodic bytes kept the connection alive beyond its total deadline"
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
    }
}

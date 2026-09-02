mod catalog;
mod protocol;
mod server;

use protocol::{PROTOCOL_VERSION, ReadyMessage, is_shutdown, parse_bootstrap};
use std::io::{self, Write};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut first = String::new();
    if io::stdin().read_line(&mut first)? == 0 {
        return Err("BOOTSTRAP_EOF".into());
    }
    let bootstrap = parse_bootstrap(first.trim_end()).map_err(|code| code.to_owned())?;
    for name in ["index.html", "app.js", "styles.css"] {
        if !bootstrap.ui_dir.join(name).is_file() {
            return Err(format!("MISSING_UI_ASSET:{name}").into());
        }
    }

    let listener = server::bind_loopback()?;
    let port = listener.local_addr()?.port();
    let ready = ReadyMessage {
        r#type: "ready",
        protocol: PROTOCOL_VERSION,
        host: "127.0.0.1",
        port,
        parent_pid: bootstrap.parent_pid,
    };
    println!("{}", serde_json::to_string(&ready)?);
    io::stdout().flush()?;

    let shutdown = Arc::new(AtomicBool::new(false));
    let watcher_flag = Arc::clone(&shutdown);
    thread::spawn(move || {
        loop {
            let mut line = String::new();
            match io::stdin().read_line(&mut line) {
                Ok(0) | Err(_) => {
                    watcher_flag.store(true, Ordering::Release);
                    break;
                }
                Ok(_) if is_shutdown(line.trim_end()) => {
                    watcher_flag.store(true, Ordering::Release);
                    break;
                }
                Ok(_) => {}
            }
        }
    });

    server::run(listener, bootstrap.ui_dir, bootstrap.token, shutdown)?;
    Ok(())
}

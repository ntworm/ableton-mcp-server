use std::path::PathBuf;

use serde::{Deserialize, Serialize};

pub const PROTOCOL_VERSION: u32 = 1;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ParentMessage {
    Bootstrap {
        protocol: u32,
        token: String,
        ui_dir: PathBuf,
        export_path: PathBuf,
        parent_pid: u32,
    },
    Shutdown {
        protocol: u32,
    },
}

#[derive(Debug)]
pub struct Bootstrap {
    pub token: String,
    pub ui_dir: PathBuf,
    pub export_path: PathBuf,
    pub parent_pid: u32,
}

#[derive(Debug, Serialize)]
pub struct ReadyMessage {
    pub r#type: &'static str,
    pub protocol: u32,
    pub host: &'static str,
    pub port: u16,
    pub parent_pid: u32,
}

pub fn parse_bootstrap(raw: &str) -> Result<Bootstrap, &'static str> {
    match serde_json::from_str(raw).map_err(|_| "INVALID_JSON")? {
        ParentMessage::Bootstrap {
            protocol,
            token,
            ui_dir,
            export_path,
            parent_pid,
        } => {
            if protocol != PROTOCOL_VERSION {
                return Err("UNSUPPORTED_PROTOCOL");
            }
            if token.len() != 64 || !token.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                return Err("INVALID_TOKEN");
            }
            if !ui_dir.is_absolute() {
                return Err("UI_DIR_NOT_ABSOLUTE");
            }
            if !export_path.is_absolute() {
                return Err("EXPORT_PATH_NOT_ABSOLUTE");
            }
            Ok(Bootstrap {
                token,
                ui_dir,
                export_path,
                parent_pid,
            })
        }
        ParentMessage::Shutdown { .. } => Err("BOOTSTRAP_REQUIRED"),
    }
}

pub fn is_shutdown(raw: &str) -> bool {
    matches!(
        serde_json::from_str(raw),
        Ok(ParentMessage::Shutdown { protocol }) if protocol == PROTOCOL_VERSION
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_wrong_protocol() {
        let raw = r#"{"type":"bootstrap","protocol":2,"token":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","ui_dir":"C:\\ui","export_path":"C:\\data\\grooves.json","parent_pid":42}"#;
        assert_eq!(parse_bootstrap(raw).unwrap_err(), "UNSUPPORTED_PROTOCOL");
    }

    #[test]
    fn rejects_short_or_non_hex_token() {
        let short =
            r#"{"type":"bootstrap","protocol":1,"token":"abc","ui_dir":"C:\\ui","export_path":"C:\\data\\grooves.json","parent_pid":42}"#;
        assert_eq!(parse_bootstrap(short).unwrap_err(), "INVALID_TOKEN");
    }

    const TOKEN: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    #[test]
    fn bootstrap_carries_the_export_path() {
        let line = format!(
            r#"{{"type":"bootstrap","protocol":1,"token":"{TOKEN}","ui_dir":"C:\\ui","export_path":"C:\\data\\grooves.json","parent_pid":42}}"#
        );
        let bootstrap = parse_bootstrap(&line).expect("parses");
        assert_eq!(
            bootstrap.export_path.to_string_lossy(),
            r"C:\data\grooves.json"
        );
    }

    #[test]
    fn bootstrap_without_an_export_path_is_refused() {
        // Starting without it would leave a helper that serves the UI and
        // answers every search with nothing, which reads as an empty seed
        // rather than a broken launch.
        let line = format!(
            r#"{{"type":"bootstrap","protocol":1,"token":"{TOKEN}","ui_dir":"C:\\ui","parent_pid":42}}"#
        );
        assert!(parse_bootstrap(&line).is_err());
    }

    #[test]
    fn a_relative_export_path_is_refused() {
        // The helper is spawned with an unspecified working directory, so a
        // relative path resolves somewhere nobody chose.
        let line = format!(
            r#"{{"type":"bootstrap","protocol":1,"token":"{TOKEN}","ui_dir":"C:\\ui","export_path":"data\\grooves.json","parent_pid":42}}"#
        );
        assert_eq!(
            parse_bootstrap(&line).unwrap_err(),
            "EXPORT_PATH_NOT_ABSOLUTE"
        );
    }
}

//! The panel URL as a scannable SVG.
//!
//! SVG rather than a raster: the modal that shows it is a webview, the image
//! has to stay sharp at whatever size Live gives it, and an SVG needs no image
//! decoder, no temporary file and no second request.

use qrcodegen::{QrCode, QrCodeEcc};

/// Quiet zone in modules. Four is the specification minimum; less and some
/// scanners refuse to lock on.
const QUIET_ZONE: i32 = 4;

pub fn svg(text: &str) -> Result<String, &'static str> {
    // Medium correction: the code is read off a screen at close range, so the
    // damage tolerance of a higher level would only buy a denser image.
    let code = QrCode::encode_text(text, QrCodeEcc::Medium).map_err(|_| "QR_TOO_LONG")?;
    let size = code.size();
    let side = size + QUIET_ZONE * 2;

    let mut path = String::new();
    for y in 0..size {
        for x in 0..size {
            if code.get_module(x, y) {
                if !path.is_empty() {
                    path.push(' ');
                }
                path.push_str(&format!("M{},{}h1v1h-1z", x + QUIET_ZONE, y + QUIET_ZONE));
            }
        }
    }

    let mut svg = String::with_capacity(path.len() + 256);
    svg.push_str(r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 "#);
    svg.push_str(&side.to_string());
    svg.push(' ');
    svg.push_str(&side.to_string());
    svg.push_str(r#"" shape-rendering="crispEdges" role="img" aria-label="QR code">"#);
    svg.push_str(r##"<rect width="100%" height="100%" fill="#ffffff"/>"##);
    svg.push_str(r#"<path d=""#);
    svg.push_str(&path);
    svg.push_str(r##"" fill="#000000"/></svg>"##);
    Ok(svg)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_url_becomes_an_svg_with_a_quiet_zone() {
        let out = svg("http://192.168.1.40:45123/picker.html#abc").unwrap();
        assert!(out.starts_with("<svg"));
        assert!(out.ends_with("</svg>"));
        // The white rect is the quiet zone: without it the dark modules run to
        // the edge and a scanner has nothing to lock on to.
        assert!(out.contains(r##"fill="#ffffff""##));
        assert!(out.contains("<path d=\"M"));
    }

    #[test]
    fn two_calls_agree() {
        let text = "http://10.0.0.5:1/picker.html#tok";
        assert_eq!(svg(text).unwrap(), svg(text).unwrap());
    }

    #[test]
    fn a_payload_too_large_to_encode_is_an_error_not_a_panic() {
        let huge = "a".repeat(8_000);
        assert!(svg(&huge).is_err());
    }
}

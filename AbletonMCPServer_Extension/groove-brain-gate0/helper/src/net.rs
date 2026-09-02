//! Who may reach the helper, and at which address it tells them to.
//!
//! Gate 1 bound loopback and refused everything else, which is why the panel
//! had to live inside Live. Reaching it from a phone means listening on the
//! local network, and that turns the bearer token from a convenience into the
//! only thing between the network and someone's Live set. Two guards make that
//! bound: the peer must be on a private network, and the token is compared in
//! constant time before any route runs.
//!
//! What this does not do is make the channel confidential. It is plain HTTP on
//! a LAN: anyone able to watch that Wi-Fi sees the token in a header. That is
//! stated here rather than implied, and it is why the token lives only as long
//! as one invocation.

use std::net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket};

/// Peers the helper will answer. Loopback for the same machine, private ranges
/// for a phone on the same Wi-Fi. A public address reaching this port means
/// something is forwarding it, and that is never what the user asked for.
pub fn is_allowed_peer(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => v4.is_loopback() || v4.is_private() || v4.is_link_local(),
        // IPv6 unique-local and link-local. Rust has no stable is_unique_local
        // for Ipv6Addr, so the fc00::/7 prefix is checked directly.
        IpAddr::V6(v6) => {
            v6.is_loopback()
                || (v6.segments()[0] & 0xfe00) == 0xfc00
                || (v6.segments()[0] & 0xffc0) == 0xfe80
        }
    }
}

/// The address a phone on the same network should be pointed at.
///
/// Asking the operating system which local address it would use to reach a
/// private destination is how you find the interface that is actually on the
/// LAN. The socket is never connected in the TCP sense and no packet is sent;
/// a UDP connect only fixes the local end.
pub fn lan_address() -> Option<Ipv4Addr> {
    let socket = UdpSocket::bind(("0.0.0.0", 0)).ok()?;
    // Any routable private address will do; nothing is sent to it.
    socket.connect(("10.255.255.255", 9)).ok()?;
    match socket.local_addr().ok()? {
        SocketAddr::V4(address) if !address.ip().is_loopback() => Some(*address.ip()),
        _ => None,
    }
}

/// The URL to show, preferring the LAN address so a phone can reach it.
pub fn panel_url(port: u16, token: &str, page: &str) -> String {
    let host = lan_address()
        .map(|ip| ip.to_string())
        .unwrap_or_else(|| "127.0.0.1".to_owned());
    format!("http://{host}:{port}/{page}#{token}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv6Addr;
    use std::str::FromStr;

    #[test]
    fn loopback_and_private_peers_are_allowed() {
        assert!(is_allowed_peer(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1))));
        assert!(is_allowed_peer(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 40))));
        assert!(is_allowed_peer(IpAddr::V4(Ipv4Addr::new(10, 0, 0, 5))));
        assert!(is_allowed_peer(IpAddr::V4(Ipv4Addr::new(172, 16, 3, 9))));
    }

    #[test]
    fn a_public_peer_is_refused() {
        // Reaching this port from a public address means something is
        // forwarding it, which is never what the user asked for.
        assert!(!is_allowed_peer(IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
        assert!(!is_allowed_peer(IpAddr::V4(Ipv4Addr::new(172, 32, 0, 1))));
        assert!(!is_allowed_peer(IpAddr::V6(
            Ipv6Addr::from_str("2001:4860:4860::8888").unwrap()
        )));
    }

    #[test]
    fn unique_local_and_link_local_v6_are_allowed() {
        assert!(is_allowed_peer(IpAddr::V6(Ipv6Addr::LOCALHOST)));
        assert!(is_allowed_peer(IpAddr::V6(
            Ipv6Addr::from_str("fd00::1").unwrap()
        )));
        assert!(is_allowed_peer(IpAddr::V6(
            Ipv6Addr::from_str("fe80::1").unwrap()
        )));
    }

    #[test]
    fn the_panel_url_carries_the_token_in_the_fragment() {
        // A fragment is never sent to the server, so the token cannot end up in
        // a request line or an access log; the page reads it and sends it as a
        // bearer header instead.
        let url = panel_url(45123, "abc", "picker.html");
        assert!(url.ends_with(":45123/picker.html#abc"));
        assert!(url.starts_with("http://"));
    }
}

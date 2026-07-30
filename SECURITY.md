# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.5.x | yes |
| 0.4.x | yes |
| 0.3.x | best-effort |
| 0.2.x | end of life |
| < 0.2 | end of life |

## Reporting a vulnerability

Please report security issues privately by emailing the maintainer listed in
the commit history (`ntworm` on GitHub). Do not open a public GitHub issue for
suspected vulnerabilities.

A useful report includes:

- A description of the impact and the attack surface (MCP tool, bridge, CLI).
- A reproduction with the tools involved (`lifecycle_status`, `save_set`,
  `run_batch`, etc.) and the bridge that was used (TCP / WebSocket).
- The Ableton Live version and the host environment (Windows version, WSL
  distribution, Node.js version for the Extension build).

The maintainer will acknowledge a report within 7 days and aim to ship a fix
in the next minor release. The CVE assignment is not promised — issues are
landed in the standard semver flow described in `CHANGELOG.md`.

## Trust boundaries

The server is intended for **local-only** use. The TCP bridge binds to
`127.0.0.1:9888` and the WebSocket bridge is intended to bind to loopback too;
do not forward either port to a LAN or tunnel. Even then, the remote Live
script side is the only authority — see `docs/KNOWN_BUGS.md` for the
documented failure modes that the code defends against.

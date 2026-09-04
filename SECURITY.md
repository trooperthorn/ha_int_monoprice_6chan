# Security Policy

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
addresses, or logs. Use GitHub's private vulnerability-reporting feature for
this repository. If private reporting is unavailable, open a minimal issue
asking the maintainer to establish a private channel; omit technical details.

Include the affected version/commit, prerequisites, impact, a minimal
reproduction, and suggested remediation. Remove tokens, API keys, cookies,
and private network details.

## Response targets

These are project targets, not an SLA: acknowledge critical/high reports in
three business days, establish severity and containment in seven, and publish
a coordinated fix/advisory as soon as safely validated. Lower-severity issues
are prioritized by exploitability and impact.

## Supported version

Only the latest published release and the default branch receive security
fixes. Operators should update Home Assistant and this integration promptly
and retain a tested rollback/backup of their configuration.

## Security boundaries

This integration is a privileged Home Assistant custom component with a
direct RS-232 link to the amplifier hardware; it is not a sandboxed or
independent security product. It trusts the local serial link (USB or a
network-attached serial gateway) and does not authenticate or encrypt
traffic on it, matching the underlying RS-232 protocol. It cannot prevent a
malicious integration in the same Python process from reading shared memory
or files. Release integrity (build provenance attestation, SBOM) covers the
supply chain from source to published asset; it makes no claim about the
security of the amplifier hardware or the network it is reachable from.

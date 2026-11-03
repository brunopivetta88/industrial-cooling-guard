# Industrial Cooling Guard

Open-source defensive tooling for industrial refrigeration, cold-chain and HVAC operators in Europe and beyond.

**Status: experimental offline detection MVP.** This release analyzes exported, complete Modbus/TCP request messages and produces JSON alerts. It does not capture live traffic, block attacks, write to PLCs or guarantee protection. It has not been validated on operational cooling equipment. BACnet, live TCP reassembly, eBPF and automatic firewall enforcement are not implemented.

## Why this project exists

Cooling availability matters to data centres, food storage and industrial operations. Operators need visibility into unexpected control changes without introducing automated shutdowns. This project offers an inspectable starting point for engineers and security teams to evaluate detection rules against their own authorized traffic.

## What works today

- Strict MBAP and request-length validation for Modbus/TCP functions 3, 4, 6 and 16.
- Detection of writes from sources outside a target's configured writer list.
- Per-device, per-unit register bounds and alerts for unmapped registers.
- Aggregate write-burst detection with bounded history, plus structured JSONL alerts.
- Reproducible offline fixtures and automated tests; no network access or third-party Python packages required.

Unsupported functions produce an `invalid_or_unsupported_request` alert. This means inspection coverage is incomplete; it does not establish malicious intent. Requests are attempts, not proof that a controller accepted a write.

## Quick start: safe offline demonstration

Requirements: Python 3.11 or newer and Git.

```sh
git clone https://github.com/brunopivetta88/industrial-cooling-guard.git
cd industrial-cooling-guard
python3 -m unittest discover -s tests -v
python3 -m icg --config examples/config.json --events examples/requests.jsonl
```

The first fixture is an allowed write and produces no alert. The second produces `unauthorized_writer` and `register_out_of_range`. The example uses documentation-only addresses; nothing is sent over a network.

## Configure for your installation

```sh
cp examples/config.json config.local.json
# Edit config.local.json using your approved asset inventory and vendor register map.
python3 -m icg --config config.local.json --events approved-requests.jsonl
```

Each input line must contain `timestamp` (finite seconds, chronological order), `source` (client identifier), `target` (server identifier) and `adu_hex` (one complete reassembled Modbus/TCP **request**, hex encoded). A trusted external exporter must distinguish requests from responses, remove retransmissions, reassemble split TCP messages and separate coalesced ADUs. Passing raw TCP segments or responses gives incorrect results. No exporter is included in this release. Stdin is supported with `--events -`.

`targets` maps server identifiers to authorized `writers` and `registers`. A register key such as `1:100` means unit ID 1 and **zero-based protocol address** 100, not vendor label 40101. Bounds are inclusive raw unsigned 16-bit values. Example bounds `[50,100]` are fictional and do not represent a safe temperature. Signed values, scaling, floating-point values, register pairs, coils and process interlocks require vendor-specific handling and are outside this release.

The write threshold is aggregate across all configured targets on one sensor, including unauthorized writes. Calibrate it for that sensor's workload. State resets when the process restarts. Targets not listed are intentionally ignored. An allowed writer may still be compromised. Configuration must be reviewed by an OT engineer before operational evaluation.

## How to reduce exposure to attacks

1. Inventory PLCs, chillers, BMS gateways and remote access paths. Remove direct Internet exposure of industrial protocols. Place OT behind a dedicated firewall and segment it from office and guest networks.
2. Allow only required engineering stations and gateways to reach the required control ports. Use a maintained remote-access gateway with MFA, individual accounts and logged, time-limited access.
3. Keep controller logic, vendor configurations and recovery instructions backed up offline. Test restoration and preserve independent physical alarms and safety controls.
4. Evaluate monitoring on a network TAP or correctly configured SPAN port first. Use a separate management interface; never insert this prototype inline. Assess packet loss and sensor health with the capture platform.
5. Establish a baseline across normal load, startup, defrost, maintenance and failover. Verify register mappings with the equipment supplier. Review false positives with operations before escalating alerts.
6. Forward alerts through your existing log collector to the SOC/SIEM, assign an owner and rehearse response. An alert should trigger investigation and the approved incident procedure. Do not wire these alerts directly to Fail2ban, CrowdSec or a shutdown relay.
7. Apply vendor-supported firmware and security updates within an approved maintenance plan. When suspicious activity is confirmed, coordinate containment with operations so essential cooling and safety remain available.

Monitoring supplements network access controls and process safety. It does not replace them. There is no verified claim here about a specific attack campaign in Europe, and this release does not claim regulatory certification.

## Deployment and limitations

Run offline analysis as an unprivileged user. Keep configurations and operational logs private; restrict log access and retention under your organization's policy. The tool has no telemetry or outbound calls. JSON events may contain sensitive asset information.

For operational pilots, provide a separately validated passive capture/export pipeline and measure end-to-end latency, packet loss, alert handling and resource use. This CLI is not a hardened high-volume collector; large input lines are checked after Python reads them, and sustained hostile input can consume CPU and log storage. Supervise the process and enforce external resource and log limits. Container and Raspberry Pi production suitability have not been benchmarked.

## Roadmap / contributions

Contributions welcome: passive capture adapters with tested TCP stream handling; BACnet inspection; device-specific register profiles; sensor health metrics; lab integrations; signed/scaled register support. Active prevention requires a separate safety-reviewed design and is not enabled by this project.

Please provide synthetic fixtures and a regression test with parser changes. Do not upload real customer captures, addresses, credentials or controller programs. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## References

- [Modbus Organization protocol specifications](https://www.modbus.org/modbus-specifications)
- [CISA: ICS defense in depth](https://www.cisa.gov/sites/default/files/recommended_practices/NCCIC_ICS-CERT_Defense_in_Depth_2016_S508C.pdf)
- [NIST SP 800-82 Rev. 3: Guide to OT Security](https://csrc.nist.gov/pubs/sp/800/82/r3/final)

## License

[MIT](LICENSE). Free to use, adapt and distribute, including commercially, subject to the license terms.

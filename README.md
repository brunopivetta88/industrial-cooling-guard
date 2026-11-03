# Industrial Cooling Guard

Open-source defensive tooling for industrial refrigeration, cold-chain and HVAC operators in Europe and beyond.

**Status: experimental, lab-first defensive toolkit.** Offline analysis and an optional passive IPv4 Modbus/TCP capture adapter produce JSON alerts. A separate **loopback-only lab gateway** can reject out-of-policy requests before forwarding them to a synthetic server. No operational cooling equipment or vendor model has been validated. This is not a production IPS or a safety controller. BACnet parsing, Modbus RTU capture, eBPF and production inline enforcement are not implemented.

## Why this project exists

Cooling availability matters to data centres, food storage and industrial operations. Operators need visibility into unexpected control changes without introducing automated shutdowns. This project offers an inspectable starting point for engineers and security teams to evaluate detection rules against their own authorized traffic.

## What works today

- Strict MBAP and request-length validation for Modbus/TCP functions 3, 4, 6 and 16.
- Detection of writes from sources outside a target's configured writer list.
- Per-device, per-unit register bounds and alerts for unmapped registers.
- Aggregate write-burst detection with bounded history, plus structured JSONL alerts.
- Signed/scaled temperature envelopes, maximum step limits and a replenishing upward-change budget to catch repeated small increases.
- Optional SYN-observed TCP reconstruction through tshark, bounded flow state and explicit coverage-gap reporting.
- A loopback lab gateway, synthetic server, restricted offline container, scheduled security analysis and dependency update proposals.
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

Each input line must contain `timestamp` (finite seconds, chronological order), `source` (client identifier), `target` (server identifier) and `adu_hex` (one complete reassembled Modbus/TCP **request**, hex encoded). Passing raw TCP segments or responses gives incorrect results. Use the experimental capture adapter below or a separately validated exporter. Stdin is supported with `--events -`.

`targets` maps server identifiers to authorized `writers` and `registers`. A register key such as `1:100` means unit ID 1 and **zero-based protocol address** 100, not vendor label 40101. Raw bounds are inclusive unsigned 16-bit values. Example bounds `[50,100]` are fictional. Optional `temperatures` rules decode one 16-bit signed or unsigned register with a positive scale and offset. Floating-point values, register pairs, coils and process interlocks are outside this release. Every installation needs the manufacturer's exact model/firmware register map.

## Temperature-change protection

See [examples/temperature-lab.json](examples/temperature-lab.json). Its fictional example decodes signed tenths of a degree, with an absolute envelope from -25 to -15, initial value -20, maximum individual step 1 and upward budget replenishment 0.5 per minute. **These are synthetic test values, not recommendations for any equipment or stored product.**

The initial upward budget equals `max_step`. Positive changes spend that budget; elapsed time refills it up to `max_step`. Downward changes do not refund it. Absolute bounds apply even after a long wait. Invalid or unauthorized transactions cannot seed a new baseline. Each register in function 16 is checked, and a failing transaction does not update temperature state.

The baseline represents accepted request values, not measured temperature or confirmed actuator state. A failed upstream response does not roll it back. State is in memory and resets on restart. The `initial` value must be independently verified when commissioning; restarts require review. Do not use this mechanism to replace physical high/low temperature cutoffs, independent sensors, controller hard limits or safety interlocks.

## Passive live capture or PCAP replay

Install tshark from your maintained OS repository or [Wireshark](https://www.wireshark.org/). Set capture permissions on the capture utility according to your OS guidance; do not run the analyzer as root.

```sh
python3 -m icg.capture --config config.local.json --pcap authorized-lab.pcap > requests.jsonl
python3 -m icg --config config.local.json --events requests.jsonl
# Live passive capture on an approved TAP/SPAN interface:
python3 -m icg.capture --config config.local.json --interface eth1 | python3 -m icg --config config.local.json --events -
```

Only request-direction IPv4 traffic to the configured server port (default 502) is exported. Capture must see the SYN. In-order split and coalesced ADUs are handled and repeated bytes skipped. Gaps, out-of-order segments, malformed MBAP and exhausted flow capacity are reported on **stderr**; affected streams are discarded until a new SYN. Streams idle for 60 seconds are discarded; at most 256 are retained. IPv6, sequence wraparound and adversarial overlapping retransmissions are not robustly supported. No alarm is evidence of safety only if coverage and health have also been verified. The adapter has unit coverage but has not been exercised with an installed tshark in this development environment.

## Try blocking in an isolated loopback lab

Start the synthetic server and gateway in separate terminals:

```sh
python3 -m icg.lab
python3 -m icg.gateway --lab-only --config examples/temperature-lab.json
```

Connect your own authorized lab client to `127.0.0.1:1502`; the synthetic server listens on `127.0.0.1:2502`. Valid writes are forwarded; out-of-policy writes receive a Modbus exception. Unsupported functions or malformed frames close the connection. The gateway checks response transaction IDs, units and function-specific response structure. It serializes requests, bounds active clients and applies I/O timeouts; it never retries an ambiguous write. Tests use in-memory transports to verify that a dangerous temperature write never reaches the upstream connection.

This gateway intentionally cannot bind to a plant network or forward to a non-loopback target. It has no TLS or client authentication. Production enforcement needs an engineered gateway, authenticated remote access, firewall rules preventing direct PLC bypass, redundant cooling, independent safety controls and vendor/operations acceptance. Blocking an unsafe command on one path cannot stop local HMI changes, alternate protocols, compromised firmware or direct access to the controller.

## Automation and updates

- Run the restricted offline container with `docker compose -f deployment/compose.yaml up --build`. It has no network, no Linux capabilities, a read-only filesystem, resource limits and rotated logs. Container execution is not validated in this environment.
- GitHub Actions runs tests for Python 3.11, 3.12 and 3.13. CodeQL runs on changes and weekly. Dependabot proposes updates for Actions and the container base. Actions are pinned to commit SHAs.
- `python3 -m icg.update_check --current YOUR_APPROVED_TAG` checks GitHub's latest stable release over HTTPS with bounded reads and a timeout. It prints JSON and installs nothing. Before the first stable release, the API returns an explicit check failure, not a false success.
- Linux update-check timer templates are provided in [deployment](deployment). They are not installed automatically. Configure the Python path, service account, code directory and currently approved version before enabling them. Review the journal with your existing alert collector.
- Never auto-replace commissioned temperature policies, controller firmware or an operational inline gateway. Validate an update in a lab, pin the approved version, retain the previous package, schedule a maintenance window and verify before returning to service. Dependency proposals and update checks automate discovery, not unattended safety-critical deployment.

## Equipment families and integration coverage

See [the integration matrix](docs/INTEGRATIONS.md) for documented Danfoss, CAREL, Eliwell, Siemens and Schneider families, plus other candidate ecosystems. Listing a brand does not mean tested compatibility. No universal register profile is shipped, and BACnet-only equipment is not inspected by the Modbus engine.

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

For operational pilots, validate the passive capture/export pipeline and measure end-to-end latency, packet loss, alert handling and resource use. Input lines are read in bounded chunks and oversized records discarded. Sustained hostile input can still consume CPU and log storage. Supervise the process and enforce external resource and log limits. Container and Raspberry Pi production suitability have not been benchmarked.

## Roadmap / contributions

Contributions welcome: stronger TCP reconstruction; BACnet inspection; verified device-specific profiles; measured-temperature correlation; persistent commissioned state; sensor health supervision; isolated hardware-in-the-loop testing. Production prevention requires a separate safety-reviewed design and is not enabled by this project.

Please provide synthetic fixtures and a regression test with parser changes. Do not upload real customer captures, addresses, credentials or controller programs. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## References

- [Modbus Organization protocol specifications](https://www.modbus.org/modbus-specifications)
- [CISA: ICS defense in depth](https://www.cisa.gov/sites/default/files/recommended_practices/NCCIC_ICS-CERT_Defense_in_Depth_2016_S508C.pdf)
- [NIST SP 800-82 Rev. 3: Guide to OT Security](https://csrc.nist.gov/pubs/sp/800/82/r3/final)

## License

[MIT](LICENSE). Free to use, adapt and distribute, including commercially, subject to the license terms.

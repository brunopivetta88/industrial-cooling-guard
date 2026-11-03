# Equipment families and evidence

This is an integration research matrix, not a market-share ranking or a compatibility certification. There is no reliable universal list of all European cooling installations. Protocol support varies by model, firmware, installed communication card and gateway. Never infer a register address or safe operating envelope from a brand name.

| Manufacturer / family | Official evidence | Current ICG coverage |
| --- | --- | --- |
| Danfoss AK-CC refrigeration controls | [AK-CC 350 product specifications](https://designcenter.danfoss.com/en-us/products/climate-solutions-for-cooling/electronic-controls/evaporator-and-room-control/ak-cc-350/p/084B4165) documents MODBUS communication options | Candidate only. Serial variants need a verified RTU-to-TCP gateway; no model profile tested. |
| CAREL MPXPRO | [Official manual](https://www.carel.com/documents/10191/0/%2B0300055EN/05b10c49-52e1-4568-804b-4c8f21d066ee?version=1.8) | Candidate only. Verify serial protocol, scaling, firmware and gateway; no profile tested. |
| Eliwell refrigeration products | [Official Modbus compatibility bulletin](https://www.eliwell.com/en/Support/Bulletins.html) | Candidate only. Exact controller must be checked against bulletin/manual. |
| Siemens Desigo / PXC | [Official Desigo overview](https://www.siemens.com/en-us/products/desigo/) describes BACnet Secure Connect | BACnet is not implemented. No compatibility claim. |
| Schneider Electric Modicon M172 / EcoStruxure HVAC | [Official BACnet application note](https://www.se.com/us/en/download/document/EIO0000005915/) | BACnet is not implemented. Any Modbus application requires its separately verified map. |

Additional requested ecosystem candidates: Daikin, Trane, Carrier, Johnson Controls/YORK, Honeywell/CentraLine, Copeland/Dixell, WAGO and Beckhoff. These names are a discovery backlog only: model, local protocol and mapping evidence have not been reviewed here. They have no shipped ICG adapters or verified compatibility. Proprietary cloud interfaces, KNX, LonWorks, BACnet/SC and serial Modbus are not interchangeable with Modbus/TCP.

## Requirements for a usable site profile

Record manufacturer, exact model, firmware, approved manual revision, transport, gateway configuration, unit IDs, address base, signedness, scaling, units and access rights. Identify every route capable of changing setpoints, operating mode, defrost, compressor enable, alarm limits and firmware. An envelope on a setpoint alone does not protect all of these routes.

Keep site asset identifiers and real network addresses in the ignored `config.local.json`. Obtain engineering approval for raw bounds, engineering-unit bounds, initial commissioned value, maximum change and rise budget. Exercise normal operation, negative temperatures, maintenance, restart, communications failure and emergency procedures in an isolated lab. Only then assess passive operational monitoring. No provided example authorizes production inline use.

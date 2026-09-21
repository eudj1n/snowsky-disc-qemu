# Firmware research

This directory owns tools used to investigate the stock firmware and establish
protocol or emulator evidence:

- [`ghidra/`](ghidra/README.md): disassembly/decompilation helpers and pinned findings.
- `diagnostics/`: ELF inspection, GDB and process-memory probes; unit tests live
  in `diagnostics/tests/`.

Start with the [RE playbook](../docs/RE.md) and
[diagnostics guide](../docs/DIAGNOSTICS.md). Reviewed runtime profiles stay in
`firmware/`; public control operations stay in `controller/`.

Runnable application prototypes live in [experiments](../experiments/README.md).
Research tools are not dependencies of Controller or the Assistant runtime.
Keep firmware, private captures and generated analysis outside Git.

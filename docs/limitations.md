# Limitations

Suite `0.1.x` is experimental. The authoritative, per-requirement list of what is and is not tested is the [gap table](gap-table.md). General limits:

- **Core only.** Optional profiles are out of scope. Restoration is used only as a path to reach Core behavior.
- **Black-box, through an adapter.** The suite observes what an adapter reports. The adapter is written by the implementer and its declaration is self-declared; the suite cannot verify that the adapter is honest or that it drives the implementation it names.
- **Self-attested results.** Hash integrity detects accidental or careless edits to a bundle, not deliberate ones. Signing is not part of this suite.
- **No concurrency or clock control.** Concurrent invocation (`D22-CON-001`) and native timestamp independence (`D22-CS4-003`) are scenarios that define no assertions yet. The runner records any such scenario as NOT EXECUTABLE for every adapter, whatever it declares, and does not send its steps. They are planned for suite `0.2.0`. Single-lineage and conflict behavior is checked sequentially, so results say nothing about thread safety.
- **Process boundary.** The suite cannot prove the absence of in-process mutable aliases, and timing and other side channels are outside the disclosure checks and are not measured.
- **No interchange or wire format.** The adapter protocol is test infrastructure. Passing the suite does not demonstrate interoperability.
- **Object Versions are opaque.** The suite compares them for equality only.

## Adapter boundary risks

- An adapter that collapses distinct outcome classes (for example authorization failure and semantic invalidity) cannot be told apart from one that reports them honestly, unless the implementation exposes the difference; such adapters report `UNMAPPABLE` or `UNCLASSIFIED`.
- Fixture behavior is defined by the suite and implemented by the adapter through the implementation's public API. How faithfully it does so is not checked beyond what the scenarios observe.

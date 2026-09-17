# DISC PEQ investigation (V2.57)

[Issue #9](https://github.com/eudj1n/snowsky-disc-qemu/issues/9) resumed by the
owner on 2026-09-17. The existing [settings contract](REMOTE_SETTINGS.md#peq-bands)
remains valid. This work separates device controls from FiiO Control's local
preset storage, Auto EQ computation and account/catalog services.
Later in the same session the owner deferred physical captures because the work
Wi-Fi prevents a reliable player connection. Resume them in this same workstream;
do not treat missing captures as absent firmware support or open a LAN bridge.

## Static device contract

Fingerprint: V2.57 stock `mq_player` SHA-256
`a5a6740435758bb3f3d008a4306c93a463c6634318957bbf32086bd7b00fabbc`.
The local analysis copy matches after normalizing only the reviewed key patch.

`4ef174` maps network preset codes to `SYSCONFIG.EQ_TYPE`:

| Wire | Stored | Stock device label |
| --- | --- | --- |
| 255 | 0 | Off |
| 0 | 1 | Jazz |
| 2 | 2 | Rock |
| 4 | 3 | R&B |
| 6 | 4 | HIP-HOP |
| 1 | 5 | Pop |
| 3 | 6 | Dance |
| 5 | 7 | Classical |
| 8 | 8 | Retro |
| 9 | 9 | Sibilance attenuation 1 |
| 10 | 10 | Sibilance attenuation 2 |
| 160..169 | 11..20 | USER1..USER10 |

Stock labels come from `set_menu/equalizer.json`, selected by UI page `4670ac`
using explicit row values 0..20; callback `466b7c` stores that value in `8e1720`.
These are device labels, not yet a captured mapping of the iPhone tiles. There
is no additional BYPASS case in this setter; do not infer its app behavior or
send guessed codes 7/254. Unknown values can leave the stored selection unchanged
while the handler echoes the supplied value.

`45e000` selects the device mode; user slots call `45d66c`, which loads their
saved parameters or initializes defaults. `4ef774` accepts JSON band writes;
`45e9e4` applies positions and explicitly sets filter type to zero, then `434fb8`
serializes the current profile. `434c94` updates `PARAMS_JSON` by `STYLE_PRESET`;
`434bc0` updates `MASTER_GAIN` with one decimal. `4f022c` → `45ed2c` persists
master gain. This establishes a device write path, not the app's Save sequence.
Keep the public band helper's type-0 restriction and conservative bounds.

## Disposable acceptance

```sh
CI_SCENARIO=peq FW_VERSION=2.57 \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The scenario checks supported preset codes against SQLite, then edits first and
last bands in each of ten user slots, verifies unchanged other bands/slots,
master gain, re-selection and restoration through both TCP and WS. It performs
no database writes. A failure aborts rather than retrying a mutation; the guest
and volume are disposable. Selection of a previously absent user slot can itself
initialize a saved profile, so this scenario must not target a personal device.
Its immediate first-use reply has Q=0.71 while the newly serialized database row
already stores Q=0.7. A later selection reloads Q=0.7. The acceptance therefore
backs up a fresh reloaded profile and requires exact restoration of that baseline;
it does not pretend the original transient precision survives serialization.
Validation results are recorded in [the research tracker](PROTOCOL_RESEARCH.md).

## Physical capture sequence

Use TCP 12100 **and** HTTP 12103. Keep raw PCAP/HAR/screenshots in ignored local
storage. Do not sign in or supply account credentials for these checks.

1. **Preset mapping:** record the original selection; select Off and each named
   factory tile, waiting 2–3 seconds between actions. Select BYPASS separately,
   then restore the original. Record the exact ordered labels alongside the
   capture. No User-band edit or Save is needed in this first capture.
2. **Device save (after the mapping capture):** use an owner-approved disposable
   User slot. First back up all ten bands, master and active preset through fresh
   device reads. Capture selecting that slot, a distinctive band/master edit,
   Save → device and the target-slot dialog. Leave/reopen it, reconnect/read back,
   then restore and verify the backup. Determine whether edits write immediately
   and what Save additionally changes; do not overwrite another personal slot.
3. **Local save:** from a known profile, Save → local data under a unique test
   name, then re-read device state. Inspect any export/share file the app offers;
   record its schema without personal/catalog content. Test local application
   separately from local storage. Do not assume saving locally leaves the device
   unchanged.
4. **Editor / Auto EQ:** record available filter types, units, displayed rounding,
   measurement/target choices, generation, Save as and explicit application to
   the disposable device slot. App-side generation and actual device commands
   require separate evidence. Keep unsupported bounds/types rejected meanwhile.
5. **Catalog scope:** classify Local, Selected/retrieval-code and Official from
   observed behavior. Account/cloud sync remains separate issue #11. A retrieval
   prompt is not device TCP authentication.

No claim of physical DSP response, exact app parity, Auto EQ implementation or
BYPASS equivalence follows from device readback alone.

## ScorpionTrack Integration

ScorpionTrack Integration gives Home Assistant a single setup flow for two ScorpionTrack sources:

- `Portal account` for the richer authenticated integration
- `Shared location link` for lightweight read-only tracking

### What it adds

- live `device_tracker` entities for Home Assistant maps and zones
- tidy `Location` sensors with raw coordinates kept in attributes
- account-level alert sensors for unread count, latest alert, and recent alert details
- account-mode vehicle sensors, binary sensors, and verified switches
- share-mode support for multiple vehicles from a single share link

### Setup options

Choose `Portal account` if you want the fuller portal-backed experience, including verified controls such as `Privacy Mode` and `Zero-Speed Mode`.

Choose `Shared location link` if you only want tracking from a ScorpionTrack share. One share can include multiple vehicles.

### Important note

The authenticated portal mode relies on private web behaviour rather than a documented public API, so it should be treated more conservatively than the shared-link mode.

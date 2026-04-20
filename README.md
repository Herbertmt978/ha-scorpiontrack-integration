[![Validate](https://github.com/Herbertmt978/ha-scorpiontrack-integration/actions/workflows/validate.yml/badge.svg)](https://github.com/Herbertmt978/ha-scorpiontrack-integration/actions/workflows/validate.yml)
[![Hassfest](https://github.com/Herbertmt978/ha-scorpiontrack-integration/actions/workflows/hassfest.yml/badge.svg)](https://github.com/Herbertmt978/ha-scorpiontrack-integration/actions/workflows/hassfest.yml)
[![GitHub Release](https://img.shields.io/github/v/release/Herbertmt978/ha-scorpiontrack-integration?display_name=tag&sort=semver)](https://github.com/Herbertmt978/ha-scorpiontrack-integration/releases)

# ScorpionTrack Integration

Home Assistant custom integration for ScorpionTrack portal accounts and shared-location links.

This integration gives Home Assistant one clean ScorpionTrack entry point with two setup options:

- `Portal account` for the richer authenticated integration
- `Shared location link` for lightweight read-only tracking

The two modes share the same polished entity model and install path, while still staying honest about the different capabilities and risks of each data source.

## Highlights

- Unified setup flow for account login or shared-location links
- Live `device_tracker` entities for Home Assistant maps and zones
- Clean `Location` sensors with combined coordinates available without cluttering the map with duplicate markers
- Account-mode alert visibility with `Unread Alerts`, `Latest Alert`, and recent alert details
- Account-mode `Mark Alerts Read` button for clearing unread portal alerts
- Account-mode switches for the portal features that have been verified as safe on/off controls
- Share-mode support for multiple vehicles from a single ScorpionTrack share
- HACS-ready repository structure, validation workflow, and brand assets

## Installation

### HACS custom repository

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the three-dot menu and choose `Custom repositories`.
4. Add `https://github.com/Herbertmt978/ha-scorpiontrack-integration`.
5. Choose `Integration` as the category.
6. Install `ScorpionTrack Integration`.
7. Restart Home Assistant.

### Manual

1. Copy `custom_components/scorpiontrack` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## Setup

Open `Settings` -> `Devices & services`, add `ScorpionTrack Integration`, then choose one of the two setup routes.

### Portal account

Choose `Portal account` when you want the fuller authenticated integration.

You will be asked for:

- your ScorpionTrack portal email
- your ScorpionTrack portal password

Account mode currently provides:

- live vehicle trackers for the Home Assistant map
- account sensors such as `Unread Alerts`, `Latest Alert`, `Latest Alert Time`, and `Vehicle Count`
- an account button named `Mark Alerts Read`
- vehicle sensors such as `Status`, `Location`, `Speed`, `Heading`, `Odometer`, `Battery Voltage`, `Fuel Type`, `Battery Type`, `Unit Make`, `MOT Due`, and more
- binary sensors such as `Ignition`, `Engine`, `Armed Mode Enabled`, `EWM Enabled`, `Driver Module Fitted`, `G-Sense Enabled`, and `Location Stale`
- verified switches for `Privacy Mode` and `Zero-Speed Mode`

### Shared location link

Choose `Shared location link` when you only want read-only tracking from a ScorpionTrack share.

To create the share in ScorpionTrack:

1. Open [ScorpionTrack Location Share](https://app.scorpiontrack.com/customer/locationshare).
2. Create a new share entry.
3. Add every vehicle you want Home Assistant to track.
4. Set an expiry that suits your use case.
5. Copy the generated share URL or token into Home Assistant.

Shared-link mode currently provides:

- `device_tracker` entities labelled with the vehicle registration or display name
- sensors such as `Status`, `Location`, `Speed`, `Heading`, `Last Reported`, and `Share Expires`
- binary sensors such as `Ignition` and `Location Stale`
- share-level sensors such as `Share Title`, `Shared By`, `Share Created`, and `Share Expires`

One share can include multiple vehicles, and the integration will import every vehicle included on that share.

## Entity Design

The integration intentionally keeps the actual map coordinates on the vehicle `device_tracker`, while the related sensors use readable location text and non-map attributes instead. That keeps Home Assistant’s map focused on one marker per vehicle instead of plotting every related sensor and status entity.

Alert sensors follow the same rule. `Latest Alert` keeps the useful alert-location details, but those coordinates are exposed as alert-specific attributes rather than generic `latitude` / `longitude`, so the alert data does not become a second map marker by accident.

Only controls that have been verified as behaving like true toggles are exposed as switches. For example:

- `Privacy Mode` is exposed as a switch
- `Zero-Speed Mode` is exposed as a switch
- `Armed Mode` is currently exposed as read-only status, not a switch, because the present portal endpoint reports it but does not reliably accept a real toggle

## Security Notes

- No live credentials or share tokens are included in this repository.
- Account mode stores the portal email and password in the Home Assistant config entry so it can refresh automatically.
- The integration does not expose the portal app API key as an entity state or attribute.
- If you open an issue, avoid posting live credentials, tokens, or screenshots that reveal current locations.
- The authenticated portal mode relies on private web behaviour, so it should be treated more conservatively than a documented public API integration.

## Development Notes

The authenticated portal work is documented in [docs/portal-notes.md](docs/portal-notes.md).

# ScorpionTrack Portal Notes

These notes capture the private portal behaviour that the authenticated account mode in the combined ScorpionTrack integration is built around.

## Login Flow

Observed on `2026-04-20`:

- `GET /home/login` returns a normal HTML login form.
- The form includes a hidden `ci_csrf_token`.
- The form posts to `POST /login/check_for_multiple_accounts`.
- The site sets session cookies such as `scorpscorpionsess` and `scorpcsrf_cookie_scorp`.

This suggests the portal uses a traditional cookie + CSRF session flow rather than a documented public token API.

## Private Endpoints Confirmed In Frontend Code

These routes were found in the current frontend bundle and are realistic targets for the authenticated integration:

- `GET /vehicles/short?limit=...`
- `GET /vehicles/search/...`
- `GET /vehicles/search/by-ids`
- `GET /vehicles/{vehicleId}/journeys/{start}/{end}...`
- `GET /alerts-dashboard/alerts`
- `GET /alerts-dashboard/summary`
- `GET /alerts-dashboard/vehicles/{vehicleId}?period=...`
- `POST /alerts-dashboard/bulk-read`
- `POST /location-shares`
- `PUT /location-shares/{shareId}`
- `POST /location-shares/{shareId}/revoke`
- `GET /speed-geofence-groups`
- `POST /speed-geofence-groups`
- `PUT /speed-geofence-groups/{groupId}`
- `DELETE /speed-geofence-groups/{groupId}`
- `POST /speed-geofence-groups/{groupId}/geofences`
- `DELETE /speed-geofence-groups/{groupId}/geofences/{geofenceId}`
- `POST /speed-geofence-groups/{groupId}/vehicles/{vehicleId}`
- `DELETE /speed-geofence-groups/{groupId}/vehicles/{vehicleId}`

## App API Key

At least one frontend path uses:

- `Authorization: Basic <base64(window.ScorpionData.user.appApiKey)>`

That key appears in the portal page JavaScript context after login. The current integration uses it for authenticated fleet API requests but does not publish it as an entity state or attribute.

## Publicly Documented Features Still To Verify

ScorpionTrack publicly documents features such as:

- transport mode
- garage mode
- privacy mode
- MOT reminders
- tax reminders
- alert settings

These are good next targets, but their exact private endpoints still need to be verified before they should be added as Home Assistant controls.

## Safety Notes

- Treat all write operations as high-trust until their semantics are confirmed.
- Do not expose theft-critical or immobilisation-related actions until the account permissions and portal behaviour are fully understood.
- Remote immobilisation appears to involve the ScorpionTrack recovery team and should not be assumed to be a normal customer self-service endpoint.

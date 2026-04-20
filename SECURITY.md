# Security Policy

## Reporting a Vulnerability

If you believe you have found a security issue in this integration:

- do not include live credentials, share tokens, or location screenshots in a public issue
- describe the behaviour, impact, and a safe way to reproduce it without secrets
- if the report needs sensitive detail, open a minimal issue first and note that you can provide the rest privately

## Scope

The main security-sensitive areas of this project are:

- handling ScorpionTrack portal credentials
- handling shared-location tokens
- avoiding unnecessary exposure of identifiers or location data in entity states and attributes
- making sure only genuinely verified controls are exposed as writable switches

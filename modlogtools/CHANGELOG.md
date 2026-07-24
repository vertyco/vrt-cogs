# 0.1.0 (2026-07-24)

- Added `[p]mywarnings` so members can view their own active warnings, points, and expiry times.
- Added `[p]modlogtool dmexpiry` to optionally DM members when their warnings expire or fully decay.
- Added `[p]modlogtool extend` for per-warning expiry overrides (`duration`, `never`, `reset`).
- Added `[p]modlogtool decay` gradual point decay mode; warnings lose points per day and are
  removed with a modlog case once they reach 0.
- Added `[p]modlogtool history` for a full pagified warning history per member.
- Hardened import/export validation, expiry loop lifecycle, and data deletion API handling.

# 0.0.1

- Initial release.

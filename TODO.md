# TODO: Fix Vendor Profile Completion Status

## Approved Plan Steps:

1. [ ] Edit `app/models/user.py`: Add `profile_complete` field to Vendor model and `is_profile_complete()` method.
2. [ ] Edit `app/schemas/schemas.py`: Add `profile_complete: bool` to VendorResponse.
3. [ ] Edit `app/routers/vendor.py`: Add logic to auto-set `profile_complete` in update_profile/shop endpoints; enhance get_vendor_profile; add `/me/completion-status` endpoint.
4. [ ] Run Alembic migration: `alembic revision --autogenerate -m "add vendor profile_complete"` then `alembic upgrade head`.
5. [ ] Test endpoints (create vendor, update profile/shop, verify status).
6. [ ] Attempt completion.

Current: Starting step 1.

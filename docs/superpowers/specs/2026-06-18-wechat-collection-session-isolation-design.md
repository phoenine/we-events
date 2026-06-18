# WeChat Collection Session Isolation Design

## Problem

Article collection runs share one persisted WeChat MP session. In all three collection modes, every non-zero WeChat response is currently classified as `Invalid Session`. The error hook then deletes the shared persisted session, while `WxGather.Error` suppresses the exception for that code. This can mark the triggering item as successful and makes later queued items fail with `请先扫码登录公众号平台`.

## Selected approach

Only WeChat response code `200003` represents an invalid session and may clear the shared persisted session. Other non-zero response codes fail only the current collection item and must not clear shared cookies. This rule applies consistently to the `app`, `api`, and `web` collection modes.

All collection errors, including `Invalid Session`, must propagate to the collection worker. The worker remains responsible for retrying the item and recording its final failure. A failed WeChat response must never be reported as a successful collection run.

## Data flow

1. A collection mode receives `base_resp.ret` from WeChat.
2. `ret == 0` continues normal collection.
3. `ret == 200003` reports `Invalid Session`; the existing error hook clears the persisted session; the error propagates to the worker.
4. Any other non-zero `ret` reports a normal collection error; the persisted session is preserved; the error propagates to the worker.
5. The worker applies the existing retry policy and records the item and run status from the propagated error.

## Scope

The change is limited to WeChat response classification and `WxGather.Error` propagation. It does not change queue concurrency, retry counts, frontend polling, login UI, or storage behavior.

## Tests

Regression tests will verify:

- A non-`200003` WeChat error propagates without invoking session cleanup.
- A `200003` response invokes session cleanup and propagates the error.
- `WxGather.Error` no longer suppresses `Invalid Session`.
- Equivalent response classification is present in `app`, `api`, and `web` modes.
- Existing backend tests continue to pass.

## Success criteria

- One account returning an unrelated WeChat error cannot delete the shared session used by queued accounts.
- A genuinely invalid session fails the current run with its real error and clears the persisted session.
- No failed collection item is marked successful because an exception was swallowed.

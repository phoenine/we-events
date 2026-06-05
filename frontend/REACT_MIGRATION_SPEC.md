# Frontend React Migration Spec

## 1. Objective

Rebuild the frontend as a React + Vite + TypeScript application and align it with the cleaned Backend + Supabase baseline.

This is a frontend rewrite, not a Vue compatibility migration. The new frontend must remove legacy product concepts and use the current backend vocabulary:

- `wechat-accounts` for WeChat official accounts.
- `wechat-account-groups` for official account groups.
- `activities` for extracted activity records.
- Frontend talks only to FastAPI under `/api/v1/wx`.
- No direct Supabase table access from frontend.

## 2. UI Direction

Primary component library:

- `antd`

Visual style reference:

- Animal Island style can be used as inspiration for empty states, welcome moments, QR authorization cards, and activity cards.
- Do not make `animal-island-ui` a core dependency in the first React baseline.
- Core tables, forms, modals, drawers, menus, pagination, uploads, notifications, and layout should use `antd`.

Design target:

- Operational tool, not marketing page.
- Dense but readable layout.
- Clear navigation, stable table layouts, predictable forms.
- Light visual personality only in low-risk surfaces such as empty states and QR panels.

## 3. Recommended Dependencies

Runtime:

```json
{
  "react": "^19",
  "react-dom": "^19",
  "react-router-dom": "^7",
  "antd": "^6",
  "@ant-design/icons": "^6",
  "@tanstack/react-query": "^5",
  "axios": "^1",
  "zustand": "^5",
  "dayjs": "^1",
  "dompurify": "^3",
  "lucide-react": "^0"
}
```

Development:

```json
{
  "@vitejs/plugin-react": "^5",
  "typescript": "^5",
  "vite": "^7",
  "eslint": "^9",
  "prettier": "^3"
}
```

Version numbers can be resolved by the package manager during implementation. If React 19 or antd 6 introduces compatibility friction, use React 18 + antd 5 as the fallback.

## 4. Target Structure

```text
frontend/src/
  api/
    http.ts
    auth.ts
    user.ts
    wechatAccounts.ts
    wechatAccountGroups.ts
    articles.ts
    activities.ts
    configs.ts
    sys.ts
  app/
    App.tsx
    router.tsx
    providers.tsx
  components/
    common/
    layout/
    feedback/
  pages/
    login/
    articles/
    wechat-accounts/
    wechat-account-groups/
    activities/
    configs/
    sys/
    user/
  store/
    authStore.ts
  types/
  utils/
  main.tsx
  styles.css
```

## 5. Pages

Required first React baseline:

- Login
- Main layout with sidebar/topbar
- Article list and article detail
- WeChat account management
- Add WeChat account from article URL
- WeChat QR authorization card
- WeChat account groups
- Activities list/detail/edit
- Config management
- System info
- Current user profile
- Change password

Explicitly excluded from the new baseline:

- RSS UI
- Webhook/notice UI
- Cron UI
- User avatar upload
- `/static/res/logo` backend asset proxy
- Old `/tags` naming
- Old `/mps` naming

## 6. API Alignment

Use `axios` with `baseURL: /api/v1`.

Current routes:

```text
POST /wx/auth/token
GET  /wx/auth/verify
GET  /wx/auth/qr/code
GET  /wx/auth/qr/url
GET  /wx/auth/qr/status
GET  /wx/auth/qr/over
POST /wx/auth/logout

GET  /wx/user
PUT  /wx/user
PUT  /wx/user/password

GET    /wx/wechat-accounts
GET    /wx/wechat-accounts/{wechat_account_id}
POST   /wx/wechat-accounts/by_article?url=...
POST   /wx/wechat-accounts
PUT    /wx/wechat-accounts/{wechat_account_id}
DELETE /wx/wechat-accounts/{wechat_account_id}
GET    /wx/wechat-accounts/update/{wechat_account_id}
GET    /wx/wechat-accounts/search/{kw}

GET    /wx/wechat-account-groups
GET    /wx/wechat-account-groups/{id}
POST   /wx/wechat-account-groups
PUT    /wx/wechat-account-groups/{id}
DELETE /wx/wechat-account-groups/{id}

GET    /wx/articles
GET    /wx/articles/{id}
GET    /wx/articles/{id}/prev
GET    /wx/articles/{id}/next
DELETE /wx/articles/{id}
DELETE /wx/articles/batch
DELETE /wx/articles/clean
DELETE /wx/articles/clean_duplicate_articles
DELETE /wx/articles/clean_expired

GET    /wx/activities
POST   /wx/activities
PUT    /wx/activities/{activity_id}
DELETE /wx/activities/{activity_id}

GET    /wx/configs
GET    /wx/configs/{key}
POST   /wx/configs
PUT    /wx/configs/{key}
DELETE /wx/configs/{key}

GET /wx/sys/info
GET /wx/sys/resources
```

## 7. Naming Rules

Frontend internal names:

- `wechatAccountId`, not `mp_id`.
- `wechatAccount`, not `mp` or `mps`.
- `wechatAccountGroup`, not `tag`.
- `logoUrl`, not `avatar`, for official account logo.
- `user profile` has no avatar in the first phase.

Legacy compatibility is not required.

## 8. QR Authorization Behavior

The QR card should:

- Call `/wx/auth/qr/code` to start a QR login session.
- Poll `/wx/auth/qr/url` until a signed image URL is available.
- Poll `/wx/auth/qr/status` for login completion.
- Show expired/error states clearly.
- Allow requesting a new QR code after timeout.

The UI should not assume the QR image is stored locally. The backend returns a signed Supabase Storage URL.

## 9. Acceptance Criteria

- No Vue runtime dependencies remain.
- No `.vue` source files remain in `frontend/src`.
- No `ant-design-vue`, `@arco-design/web-vue`, `vue-router`, or `@vitejs/plugin-vue`.
- `npm/pnpm build` succeeds.
- Dev server proxies `/api` to FastAPI.
- No frontend calls to deleted backend routes:
  - `/wx/mps`
  - `/wx/tags`
  - `/wx/user/avatar`
  - `/static/res/logo`
  - `/rss`
  - `/feed`
- Login, QR authorization, article list, account management, activities, config, and sys info pages are usable.

## 10. Implementation Strategy

1. Replace Vue dependencies and Vite plugin with React dependencies.
2. Replace `src` with the React structure.
3. Implement API clients first.
4. Implement auth store, HTTP interceptors, and route guard.
5. Implement layout and navigation.
6. Implement pages in this order:
   - Login
   - QR authorization card
   - WeChat accounts
   - Articles
   - Activities
   - Groups
   - Configs
   - Sys/user pages
7. Run build and route smoke checks.


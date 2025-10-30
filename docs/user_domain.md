# User Domain Entity Overview

```
+-----------------+           +--------------------+
|  subscriptions  |<---+     |     user_profiles  |
|-----------------|    |     |--------------------|
| id (PK)         |    |     | id (PK)            |
| name (UNIQUE)   |    |     | user_id (FK, uniq) |
| level           |    +-----| telegram_id (uniq) |
| monthly_cost    |          | ...                |
| created_at      |          | created_at         |
| updated_at      |          | updated_at         |
+-----------------+          | deleted_at         |
                             +---------^----------+
                                       |
                                       |
+-----------------+           +--------+----------+
|      users      |1---------n|     user_sessions  |
|-----------------|           |--------------------|
| id (PK)         |           | id (PK)            |
| email (UNIQUE)  |           | user_id (FK)       |
| hashed_password |           | session_token uniq |
| role (Enum)     |           | expires_at         |
| balance         |           | created_at         |
| subscription_id |-----------| revoked_at         |
| is_active       |           | ended_at           |
| created_at      |           +--------------------+
| updated_at      |
| deleted_at      |
+-----------------+
```

* **Subscriptions** represent purchasable plans. Users may reference a subscription, and the reference is nulled if the subscription is removed.
* **Users** own a single profile and many sessions. Soft deletion is handled via `deleted_at`.
* **User Profiles** extend the main user entity with optional contact data. The `telegram_id` column is globally unique.
* **User Sessions** track issued auth tokens, cascading away when the owning user is deleted.

Key business rules validated by the automated tests:

- `users.email` and `user_profiles.telegram_id` are unique.
- Deleting a user removes related profiles and sessions (via database cascades).
- Balance adjustments preserve two-decimal precision.
- Session lifecycle helpers (create/revoke/expire) update timestamps consistently.
```

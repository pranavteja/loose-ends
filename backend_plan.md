# Voice Notes / Calendar Booking API — Context Reset Prompt

You are continuing a hackathon project. This file is the source of truth for the design decisions made so far. Follow it exactly unless I explicitly ask to change something.

## 0. Current status

- Design/LLD is done.
- No implementation code has been written yet.
- Working folder should be: `C:\repos\voice-notes`
- Do not introduce GSI. All lookups must be simple direct GetItem/Query lookups.

## 1. Product goal

Build a backend API where the user gives voice commands to create calendar bookings.

Example flow:

1. User says: "Book a cafe visit with Sara from 3 to 5 PM today."
2. Backend processes voice, extracts `fromDate`, `toDate`, `userId`, etc.
3. If `location` is missing, backend returns text + JSON + optional audio:
   "Which location do you want to book?"
4. User says: "Jayanagar."
5. Backend appends location to the same session JSON.
6. Once all fields are valid, backend asks for confirmation.
7. User confirms with "ok / yes / confirm".
8. `POST /confirmation` saves the booking in the `bookings` table.

Important correction:
- Voice output itself does NOT create the booking.
- Booking is created only when `POST /confirmation` succeeds.

## 2. Technical stack

- Backend: Python + FastAPI on AWS EC2
- Frontend: S3 + CloudFront, but ignore frontend implementation for now
- Database: AWS DynamoDB
- Voice-to-text: OpenAI Whisper / OpenAI speech-to-text
- Text-to-speech: optional, return audio as base64 mp3
- Auth: custom JWT, no external OAuth/Cognito
- Audio files are processed but not stored

## 3. DynamoDB tables

There are exactly 2 tables.

---

### Table 1: `userProfiles`

Keys:

```text
Partition key: userId
Sort key: userEmail
```

No GSI.

This table stores 3 entity types:

#### 3.1 Profile item

```json
{
  "userId": "u_123",
  "userEmail": "sara@example.com",
  "entityType": "PROFILE",
  "username": "sara",
  "password": "hiddenOrHashedValue",
  "activeSessionId": "session-1"
}
```

Rules:
- `GET /userProfile` must never return `password`.
- Password is hidden from API responses.

#### 3.2 Username lookup item

Needed because there is no GSI and login is by username.

```json
{
  "userId": "USERNAME#sara",
  "userEmail": "LOOKUP",
  "entityType": "USERNAME_LOOKUP",
  "actualUserId": "u_123"
}
```

Login lookup:

```text
GetItem(PK = USERNAME#<username>, SK = LOOKUP)
→ actualUserId

GetItem(PK = actualUserId, SK = userEmail)
→ profile
```

#### 3.3 Chat session item

One chat session item per booking conversation.

`session-1`, `session-2`, `session-3` are separate booking conversations.

Inside one session, each voice callback is a `turn`, not a new session.

```json
{
  "userId": "u_123",
  "userEmail": "SESSION#session-1",
  "entityType": "CHAT_SESSION",
  "sessionId": "session-1",
  "fromDate": "2026-11-18T15:00:00",
  "toDate": "2026-11-18T17:00:00",
  "location": null,
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "text": "Book a cafe visit from 3 to 5 PM today"
    },
    {
      "turn": 1,
      "role": "assistant",
      "text": "Which location do you want to book?"
    }
  ],
  "missingFields": ["location"],
  "status": "AWAITING_LOCATION"
}
```

After second voice input, update the same item:

```json
{
  "userId": "u_123",
  "userEmail": "SESSION#session-1",
  "entityType": "CHAT_SESSION",
  "sessionId": "session-1",
  "fromDate": "2026-11-18T15:00:00",
  "toDate": "2026-11-18T17:00:00",
  "location": "Jayanagar",
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "text": "Book a cafe visit from 3 to 5 PM today"
    },
    {
      "turn": 1,
      "role": "assistant",
      "text": "Which location do you want to book?"
    },
    {
      "turn": 2,
      "role": "user",
      "text": "Jayanagar"
    }
  ],
  "missingFields": [],
  "status": "READY_TO_CONFIRM"
}
```

After successful confirmation:

```json
{
  "status": "BOOKED",
  "bookingId": "booking_1"
}
```

Also update profile:

```json
{
  "activeSessionId": null,
  "lastBookingId": "booking_1"
}
```

---

### Table 2: `bookings`

Keys:

```text
Partition key: userId
Sort key: fromDate
```

LSI:

```text
LSI name: bookingIdIndex
LSI partition key: userId
LSI sort key: bookingId
```

No GSI.

LSI must be defined when the table is created.

Example booking item:

```json
{
  "userId": "u_123",
  "fromDate": "2026-11-18T15:00:00",
  "bookingId": "booking_1",
  "toDate": "2026-11-18T17:00:00",
  "location": "Jayanagar",
  "status": "BOOKED",
  "sessionId": "session-1"
}
```

Rules:
- `fromDate` must be an ISO timestamp string.
- Same user + same `fromDate` should be treated as a conflict/duplicate.
- Save booking only after `/confirmation`.

## 4. Query rules

No GSI.

### Calendar list query

Endpoint:

```http
GET /calendar?fromDate=2026-11-18T00:00:00&toDate=2026-11-18T23:59:59
```

DynamoDB query:

```text
userId from JWT
AND fromDate BETWEEN :fromDate AND :toDate
```

### Collision check

Do not rely only on the narrow requested range, because an existing booking like 14:00–16:00 overlaps a requested 15:00–17:00 booking but starts before `fromDate`.

For collision check:
1. Query bookings for the full relevant day/date window.
2. Check overlap in application code:

```text
existing.fromDate < requested.toDate
AND existing.toDate > requested.fromDate
```

## 5. APIs

All APIs except register/login/health require:

```http
Authorization: Bearer <jwt>
```

---

### 5.1 `POST /register`

Request:

```json
{
  "username": "sara",
  "email": "sara@example.com",
  "password": "hiddenValue"
}
```

Response:

```json
{
  "userId": "u_123",
  "username": "sara",
  "email": "sara@example.com"
}
```

Backend writes:
1. Profile item
2. Username lookup item

---

### 5.2 `POST /userlogin`

Request:

```json
{
  "username": "sara",
  "password": "hiddenValue"
}
```

Response:

```json
{
  "token": "<jwt>",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "user": {
    "userId": "u_123",
    "username": "sara",
    "email": "sara@example.com"
  }
}
```

JWT payload:

```json
{
  "userId": "u_123",
  "username": "sara",
  "email": "sara@example.com",
  "exp": 1760003600
}
```

Frontend storage is ignored for now.

---

### 5.3 `GET /userProfile`

Response must exclude password:

```json
{
  "userId": "u_123",
  "username": "sara",
  "email": "sara@example.com",
  "activeSessionId": "session-1"
}
```

---

### 5.4 `POST /voiceInput`

Content type:

```text
multipart/form-data
```

Fields:

```text
audio: <file>
sessionId: session-1
```

`userId` must be taken from JWT, not request body.

Backend steps:
1. Receive audio file.
2. Convert audio to transcript using OpenAI speech-to-text.
3. Parse transcript into fields.
4. Load/create chat session item in `userProfiles`.
5. Append user message to `messages`.
6. Update `fromDate`, `toDate`, and/or `location`.
7. Check missing fields.
8. Check booking collision.
9. Return text + JSON + optional audio.

Response when location missing:

```json
{
  "sessionId": "session-1",
  "turn": 1,
  "stage": "AWAITING_LOCATION",
  "text": "Which location do you want to book?",
  "voiceOutput": {
    "format": "mp3",
    "base64": "<optional-audio-base64>"
  },
  "session": {
    "sessionId": "session-1",
    "fromDate": "2026-11-18T15:00:00",
    "toDate": "2026-11-18T17:00:00",
    "location": null,
    "missingFields": ["location"],
    "status": "AWAITING_LOCATION"
  }
}
```

Response when all fields are complete:

```json
{
  "sessionId": "session-1",
  "turn": 2,
  "stage": "READY_TO_CONFIRM",
  "text": "You want to book Jayanagar from 3 PM to 5 PM today. Should I confirm?",
  "voiceOutput": {
    "format": "mp3",
    "base64": "<optional-audio-base64>"
  },
  "session": {
    "sessionId": "session-1",
    "fromDate": "2026-11-18T15:00:00",
    "toDate": "2026-11-18T17:00:00",
    "location": "Jayanagar",
    "missingFields": [],
    "status": "READY_TO_CONFIRM"
  }
}
```

---

### 5.5 `POST /confirmation`

Request:

```json
{
  "sessionId": "session-1",
  "confirm": true,
  "finalJson": {
    "userId": "u_123",
    "fromDate": "2026-11-18T15:00:00",
    "toDate": "2026-11-18T17:00:00",
    "location": "Jayanagar"
  }
}
```

Backend must:
1. Read session from `userProfiles`.
2. Re-validate all fields.
3. Re-check collision.
4. Save item in `bookings`.
5. Update session status to `BOOKED`.
6. Update user profile `activeSessionId` to `null`.
7. Return booking result.

Response:

```json
{
  "status": "BOOKED",
  "bookingId": "booking_1",
  "sessionId": "session-1",
  "text": "Done. Your booking is confirmed."
}
```

Repeated confirm must not create duplicate bookings.

---

### 5.6 `GET /calendar`

```http
GET /calendar?fromDate=2026-11-18T00:00:00&toDate=2026-11-18T23:59:59
```

Response:

```json
{
  "events": [
    {
      "bookingId": "booking_1",
      "fromDate": "2026-11-18T15:00:00",
      "toDate": "2026-11-18T17:00:00",
      "location": "Jayanagar",
      "status": "BOOKED"
    }
  ]
}
```

---

### 5.7 `GET /health`

Optional simple health endpoint.

```json
{
  "status": "ok"
}
```

## 6. Session status values

Use these statuses in chat session JSON:

```text
AWAITING_LOCATION
READY_TO_CONFIRM
BOOKED
CONFLICT
ERROR
CANCELLED
```

Use these API stage values in `/voiceInput`:

```text
AWAITING_LOCATION
READY_TO_CONFIRM
BOOKED
CONFLICT
ERROR
```

## 7. Important constraints

- No GSI.
- Only 2 tables: `userProfiles` and `bookings`.
- Chat sessions live inside `userProfiles` as separate items.
- Bookings live in `bookings`.
- `POST /confirmation` is the only place that writes to `bookings`.
- Voice output is optional and returned as base64 mp3.
- Audio files are not stored.
- `userId` always comes from JWT, never from request body.
- `GET /userProfile` never returns password.
- `fromDate` is the bookings sort key and must be ISO timestamp format.

## 8. Next implementation milestone

Start with backend scaffolding:

1. Create FastAPI project structure.
2. Add config for DynamoDB table names and JWT secret.
3. Implement DynamoDB client helper.
4. Implement `/register`.
5. Implement `/userlogin`.
6. Implement JWT auth dependency.
7. Implement `/userProfile`.
8. Then move to `/voiceInput`.
9. Then `/confirmation`.
10. Then `/calendar`.

Do not add extra tables, GSI, Cognito, OAuth, S3 audio storage, or frontend code unless asked.

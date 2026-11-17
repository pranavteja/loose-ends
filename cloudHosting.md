# AWS Hosting Plan — Voice Notes / Calendar Booking API

This file explains how we will host the hackathon version of the application.

## 1. Hosting architecture

```text
User browser
   |
   | https://dxxxxx.cloudfront.net
   v
CloudFront distribution
   |
   |-- default behavior --> S3 bucket (Angular/React static build)
   |
   |-- /api/* behavior ---> EC2 Elastic IP : 80
                              |
                              | Nginx reverse proxy
                              v
                         FastAPI on 127.0.0.1:8000
                              |
                              |-- OpenAI speech-to-text / agent / TTS
                              |
                              |-- DynamoDB (userProfiles, bookings)
```

### Key decisions

- Frontend: static Angular or React app hosted in S3 and served by CloudFront.
- Backend: FastAPI running on EC2.
- EC2 gets an **Elastic IP** so the origin address is stable.
- No DNS / Route53 / custom domain for the hackathon.
- No S3 bucket for voice files.
- Browser records mp3/webm and posts it directly to the backend.
- Backend sends the audio to OpenAI and gets back strict JSON.
- OpenAI API key and JWT secret are stored as SSM Parameter Store SecureString values.
- EC2 accesses DynamoDB through an IAM instance profile.
- CloudFront proxies `/api/*` to EC2 so the browser calls the same HTTPS domain and avoids mixed-content issues.

---

## 2. AWS resources to create

| Resource | Purpose |
|---|---|
| S3 bucket | Static frontend build files |
| CloudFront distribution | Public HTTPS frontend URL + `/api/*` proxy |
| EC2 instance | FastAPI backend |
| Elastic IP | Stable public IP for EC2 |
| IAM role for EC2 | DynamoDB access, SSM read, CloudWatch logs |
| DynamoDB table `userProfiles` | Profile, username lookup, chat sessions |
| DynamoDB table `bookings` | Final calendar bookings |
| SSM SecureString parameters | OpenAI key, JWT secret |
| Security group | Controls access to EC2 |

---

## 3. DynamoDB tables

Create these before deploying the backend.

### 3.1 `userProfiles`

Keys:

```text
PK: userId
SK: userEmail
```

No GSI, no LSI.

```sh
aws dynamodb create-table \
  --table-name userProfiles \
  --attribute-definitions \
    AttributeName=userId,AttributeType=S \
    AttributeName=userEmail,AttributeType=S \
  --key-schema \
    AttributeName=userId,KeyType=HASH \
    AttributeName=userEmail,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

### 3.2 `bookings`

Keys:

```text
PK: userId
SK: fromDate
LSI: bookingIdIndex (PK userId, SK bookingId)
```

No GSI.

The LSI must be created with the table.

```sh
aws dynamodb create-table \
  --table-name bookings \
  --attribute-definitions \
    AttributeName=userId,AttributeType=S \
    AttributeName=fromDate,AttributeType=S \
    AttributeName=bookingId,AttributeType=S \
  --key-schema \
    AttributeName=userId,KeyType=HASH \
    AttributeName=fromDate,KeyType=RANGE \
  --local-secondary-indexes '[
    {
      "IndexName": "bookingIdIndex",
      "KeySchema": [
        { "AttributeName": "userId", "KeyType": "HASH" },
        { "AttributeName": "bookingId", "KeyType": "RANGE" }
      ],
      "Projection": { "ProjectionType": "ALL" }
    }
  ]' \
  --billing-mode PAY_PER_REQUEST
```

---

## 4. SSM Parameter Store values

Store secrets here, not in GitHub and not in frontend code.

```sh
aws ssm put-parameter \
  --name /voice-notes/openai-api-key \
  --type SecureString \
  --value "REPLACE_WITH_OPENAI_KEY" \
  --overwrite

aws ssm put-parameter \
  --name /voice-notes/jwt-secret \
  --type SecureString \
  --value "REPLACE_WITH_LONG_RANDOM_SECRET" \
  --overwrite
```

Backend reads these at startup using boto3.

For local development only, we can use environment variables:

```text
OPENAI_API_KEY=...
JWT_SECRET=...
DYNAMODB_USERS_TABLE=userProfiles
DYNAMODB_BOOKINGS_TABLE=bookings
AWS_REGION=ap-south-1
```

---

## 5. EC2 IAM role

Attach an IAM role to the EC2 instance. Do not put AWS access keys on the server.

Policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/userProfiles",
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/bookings",
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/bookings/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/voice-notes/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

Replace `REGION` and `ACCOUNT_ID`.

---

## 6. EC2 setup

Recommended for hackathon:

- Amazon Linux 2023
- `t3.small` or `t3.micro`
- Elastic IP attached
- Security group rules:

| Port | Source | Purpose |
|---|---|---|
| 22 | My IP only | SSH |
| 80 | CloudFront origin-facing prefix list, or `0.0.0.0/0` for hackathon | HTTP proxy |
| 443 | Not needed on EC2 | CloudFront handles HTTPS |

### Install basics

```sh
sudo dnf update -y
sudo dnf install python3 python3-pip nginx git -y
```

### Deploy backend

```sh
sudo mkdir -p /opt/voice-notes
cd /opt/voice-notes

python3 -m venv venv
source venv/bin/activate

pip install fastapi uvicorn boto3 python-jose passlib python-multipart httpx openai
```

Copy the FastAPI project into `/opt/voice-notes/app`.

Run locally on the instance:

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Nginx reverse proxy

Create:

```sh
sudo nano /etc/nginx/conf.d/voice-notes.conf
```

Config:

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 25M;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Content-Type $content_type;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
```

Restart Nginx:

```sh
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl restart nginx
```

With this setup:

```text
/api/register  -> backend /register
/api/voiceInput -> backend /voiceInput
```

---

## 7. Frontend hosting on S3 + CloudFront

Frontend framework is still undecided: Angular or React.

Both build to static files:

```text
React    -> build/  or dist/
Angular  -> dist/<app-name>/
```

### S3 bucket

- Create a private S3 bucket.
- Keep Block Public Access enabled.
- Use CloudFront Origin Access Control (OAC) to read the bucket.
- Upload build output.

Example:

```sh
aws s3 sync ./dist s3://YOUR_FRONTEND_BUCKET --delete
```

### CloudFront distribution

Create one distribution with two origins.

#### Origin 1: S3

- Origin type: S3 bucket
- Access: Origin Access Control
- Default behavior: S3 origin

#### Origin 2: EC2

- Origin domain: Elastic IP or EC2 public DNS
- Protocol: HTTP
- Behavior path: `/api/*`

#### `/api/*` behavior settings

| Setting | Value |
|---|---|
| Origin | EC2 |
| Viewer protocol policy | Redirect HTTP to HTTPS |
| Allowed methods | GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS |
| Cache policy | CachingDisabled |
| Origin request policy | AllViewer |
| Compress | No for API is fine |

This forwards:

- Authorization header
- Content-Type
- request body
- query string

So JWT auth and mp3 upload work correctly.

### SPA routing

For Angular/React client-side routes, add custom error responses:

```text
403 -> 200 /index.html
404 -> 200 /index.html
```

### Public URL

No DNS needed.

Use the CloudFront default domain:

```text
https://dxxxxx.cloudfront.net
```

Frontend calls:

```text
https://dxxxxx.cloudfront.net/api/register
https://dxxxxx.cloudfront.net/api/voiceInput
https://dxxxxx.cloudfront.net/api/calendar
```

This avoids mixed-content issues because both frontend and API are on the same HTTPS CloudFront domain.

---

## 8. Voice/audio flow

No audio is stored in S3.

```text
Browser records mp3/webm
  -> POST /api/voiceInput (multipart/form-data)
  -> Nginx
  -> FastAPI
  -> OpenAI speech-to-text / agent
  -> strict JSON with text
  -> browser
  -> browser SpeechSynthesis speaks the text locally
```

Backend must enforce upload size, e.g. 20–25 MB.

Default for the hackathon:
- Backend returns only text + JSON.
- Frontend speaks `text` using the browser SpeechSynthesis API.
- No backend TTS and no base64 mp3 response are needed.
- Browser dictation / Web Speech API can still be used as an input fallback.

Angular service example:

```ts
// speech.service.ts
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class SpeechService {
  speak(text?: string | null): void {
    if (!text || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 1;

    window.speechSynthesis.speak(utterance);
  }
}
```

Usage after `POST /api/voiceInput`:

```ts
if (
  response.stage === 'AWAITING_LOCATION' ||
  response.stage === 'CONFLICT' ||
  response.stage === 'READY_TO_CONFIRM'
) {
  this.speech.speak(response.text);
}
```

Browsers usually require speech to start from a user gesture, so call this after the voice button click/response flow.

---

## 9. OpenAI agent JSON contract

Ask the OpenAI agent to return exactly 5 fields:

```json
{
  "userId": "u_123",
  "fromDate": "2026-11-18T15:00:00",
  "toDate": "2026-11-18T17:00:00",
  "location": null,
  "message": "Which location do you want to book?"
}
```

Rules:

- `userId` from JWT is authoritative. Backend overwrites whatever agent returns.
- `location` can be `null`.
- `message` is the assistant response text and can be converted to voice.
- Backend validates this JSON before using it.
- Check booking collision before asking for missing location.
- If a booking overlaps, return stage `CONFLICT` with the existing booking details and ask the user to reselect the time.
- If no collision and `location` is missing, return stage `AWAITING_LOCATION`.
- If all fields are valid, return stage `READY_TO_CONFIRM`.
- A `CONFLICT` response never writes to DynamoDB `bookings`.
- Only `/confirmation` writes to DynamoDB `bookings`.

---

## 10. Deployment order

1. Create DynamoDB tables.
2. Create SSM SecureString parameters.
3. Create IAM role and attach to EC2.
4. Launch EC2 and attach Elastic IP.
5. Install Python, Nginx, and backend dependencies.
6. Deploy FastAPI app.
7. Start backend with systemd or nohup for hackathon.
8. Test directly:
   ```sh
   curl http://EC2_PUBLIC_IP/health
   ```
9. Configure Nginx `/api/*` proxy.
10. Test through EC2:
   ```sh
   curl http://EC2_PUBLIC_IP/api/health
   ```
11. Upload frontend build to S3.
12. Create CloudFront distribution with S3 + EC2 origins.
13. Test:
   ```text
   https://dxxxxx.cloudfront.net
   https://dxxxxx.cloudfront.net/api/health
   ```
14. Invalidate CloudFront after frontend changes:
   ```sh
   aws cloudfront create-invalidation \
     --distribution-id DISTRIBUTION_ID \
     --paths "/*"
   ```

---

## 11. Hackathon-safe simplifications

Allowed:

- EC2 public Elastic IP
- CloudFront default domain, no custom DNS
- HTTP from CloudFront to EC2
- Caching disabled for API
- SSM SecureString instead of full secrets manager setup
- No S3 audio storage
- Browser dictation fallback

Avoid:

- Committing API keys to Git
- Hardcoding AWS credentials on EC2
- Allowing SSH from `0.0.0.0/0`
- Serving frontend over HTTP while API is HTTPS
- Creating extra DynamoDB tables or GSI without updating the context plan

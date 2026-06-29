# XiaoYueDict - Backend

Django REST API Gateway + Celery Task Queue + Microservices

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Django-4.2+-092E20?style=flat-square&logo=django&logoColor=white" />
  <img src="https://img.shields.io/badge/DRF-3.15-A30000?style=flat-square&logo=django&logoColor=white" />
  <img src="https://img.shields.io/badge/Celery-5.x-37814A?style=flat-square&logo=celery&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white" />
</p>

---

## Statistics

| Metric | Value |
|---|---|
| **Django Apps** | **12** |
| Source files | 131 files |
| Lines of code | 12,441 LOC |
| Database migrations | 39 applied |
| Celery scheduled tasks | 4 |
| API endpoints | 12 URL namespaces |
| Docker containers (backend) | 7 (Django, 4 Celery workers, Beat, DB) |

---

## System Architecture

```
[Client (Next.js / Mobile)]
           │
           │ HTTPS / WSS
           ▼
[ Nginx Reverse Proxy (80/443) ]
     ├── /api/core/*  ──► [ Django API Gateway (8080) ]
     │                         ├── Database: [ PostgreSQL (5432) ]
     │                         ├── Cache: [ Redis (6379 / DB 1) ]
     │                         └── Internal Microservice Calls:
     │                                ├── [ AI English Scorer (8000) ]
     │                                └── [ AI Chinese Scorer (8001) ]
     │
     ├── /ws/*        ──► [ WebSocket Gateway (8005) ]
     │                         └── Pub/Sub: [ Redis (6379 / DB 0) ]
     │
     ├── /api/v1/tts  ──► [ TTS Service (8002) ]
     │                         └── Storage: [ Google Cloud Storage ]
     │
     └── /static/* & /media/* (Served directly from Docker Volumes)

[ Django API Gateway (8080) ] ──► Queue Broker (Redis DB 0) ──► [ Celery Workers (4 tiers) ]
                                                                      ├── [ Image Service (8003) ] (Imagen 4.0)
                                                                      └── [ PDF Service (8082) ] (ReportLab)
```

---

## Codebase Architecture

```
core_django/
├── core_project/                 # Django project settings
│   ├── settings.py               # Config, CORS, JWT, Celery, Cache
│   ├── urls.py                   # Root URL routing (12 API namespaces)
│   ├── authentication.py         # Cookie-based JWT auth
│   ├── celery.py                 # Celery app config
│   └── ws_utils.py               # WebSocket notification helper
│
├── apps/
│   ├── dictionary_zh/            # Chinese Dictionary
│   │   ├── models.py             #    ZhWord, ZhExample (HSK 1-6)
│   │   ├── views.py              #    Full-text search (jieba + trigram)
│   │   ├── tasks.py              #    AI translation (Gemini 2.5 Flash)
│   │   └── urls.py               #    /api/v1/dictionary/zh/
│   │
│   ├── dictionary_en/            # English Dictionary
│   │   ├── models.py             #    EnWord, EnDefinition, EnExample
│   │   ├── views.py              #    Full-text search + frequency ranking
│   │   └── urls.py               #    /api/v1/dictionary/en/
│   │
│   ├── assessments/              # Pronunciation Assessment
│   │   ├── models.py             #    AssessmentTask (async queue)
│   │   ├── views.py              #    Upload audio -> AI scoring
│   │   ├── tasks.py              #    Celery: proxy to AI services
│   │   └── urls.py               #    /api/v1/assessments/
│   │
│   ├── exams/                    # Exam Management
│   │   ├── models.py             #    Exam, ExamQuestion, ExamQuestionGroup
│   │   ├── views.py              #    Fetch exams, media streaming
│   │   ├── tasks.py              #    Import exam + process media
│   │   └── urls.py               #    /api/v1/exams/
│   │
│   ├── notes/                    # Notebook & PDF Export
│   │   ├── models.py             #    Notebook, NoteWord, PdfExport
│   │   ├── views.py              #    CRUD notebooks, export PDF
│   │   ├── tasks.py              #    Async PDF generation
│   │   └── urls.py               #    /api/v1/notes/
│   │
│   ├── media/                    # AI Image Orchestration
│   │   ├── models.py             #    ZhEnMapping (cross-language bridge)
│   │   ├── views.py              #    Image status + trigger generation
│   │   ├── tasks.py              #    Celery -> Image Service -> GCS
│   │   └── urls.py               #    /api/v1/media/
│   │
│   ├── subscriptions/            # Subscription & Payments
│   │   ├── models.py             #    SubscriptionPlan, UserSubscription, PaymentOrder
│   │   ├── views.py              #    Register, upgrade, downgrade, SePay webhook
│   │   ├── middleware.py         #    VolumeLimitMiddleware (bandwidth tracking)
│   │   ├── tasks.py              #    Expiry, pending orders cleanup
│   │   └── urls.py               #    /api/v1/subscriptions/
│   │
│   ├── users/                    # User Management
│   │   ├── models.py             #    CustomUser (firebase_uid, avatar, tier)
│   │   ├── views.py              #    Firebase login, profile update
│   │   └── urls.py               #    /api/v1/users/
│   │
│   ├── gamification/             # Gamification & Streaks
│   │   ├── models.py             #    UserStreak, DailyActivity
│   │   ├── views.py              #    Dashboard stats, heatmap data
│   │   └── urls.py               #    /api/v1/gamification/
│   │
│   ├── notifications/            # Push Notifications
│   │   ├── models.py             #    Notification (with expiry)
│   │   ├── views.py              #    List, mark read, clear
│   │   └── urls.py               #    /api/v1/notifications/
│   │
│   ├── reports/                  # Reports & Support Tickets
│   │   ├── models.py             #    ContentReport, SupportRequest, FeatureReport
│   │   ├── views.py              #    Submit report, support ticket CRUD
│   │   └── urls.py               #    /api/v1/reports/
│   │
│   └── core_shared/              # Shared utilities
│       └── throttles.py          #    Dynamic throttle scopes
│
├── manage.py
├── requirements.txt
└── Dockerfile
```

---

## API Endpoints

| Namespace | Prefix | Description |
|---|---|---|
| `dictionary_zh` | `/api/v1/dictionary/zh/` | Chinese dictionary, search, translation |
| `dictionary_en` | `/api/v1/dictionary/en/` | English dictionary, definitions |
| `assessments` | `/api/v1/assessments/` | Upload audio, pronunciation scoring |
| `exams` | `/api/v1/exams/` | Exam lists, audio streaming |
| `notes` | `/api/v1/notes/` | Notebook CRUD, PDF export |
| `media` | `/api/v1/media/` | Image generation, status polling |
| `subscriptions` | `/api/v1/subscriptions/` | Subscription plans, registration, payment webhook |
| `users` | `/api/v1/users/` | Firebase authentication, profile management |
| `gamification` | `/api/v1/gamification/` | Streak statistics, daily contribution heatmap |
| `notifications` | `/api/v1/notifications/` | Push notification management |
| `reports` | `/api/v1/reports/` | Content reports, support tickets |
| `admin` | `/admin/` | Django Admin panel |

---

## Celery Task Queue

### Queue Architecture (4-tier)

```
┌─────────────────────────────────────────────────┐
│              Celery Beat (Scheduler)             │
│  - calculate_daily_streaks      (0:00 daily)     │
│  - process_expired_subscriptions (0:30 daily)    │
│  - purge_old_pdf_exports        (hourly)         │
│  - expire_pending_payment_orders (every 5 min)   │
└──────────────────────┬──────────────────────────┘
                       ▼
┌──────────┬──────────┬──────────┬──────────┐
│queue_core│queue_paid│queue_free│queue_guest│
│          │          │          │          │
│- Image   │- AI Paid │- AI Free │- AI Guest│
│  Gen     │  Scoring │  Scoring │  Scoring │
│- Transla-│          │          │          │
│  tion    │          │          │          │
│- PDF Gen │          │          │          │
└──────────┘──────────┘──────────┘──────────┘
   Worker     Worker     Worker     Worker
   (conc=2)   (conc=1)   (conc=1)   (conc=1)
```

### Async Tasks

| Task | Queue | Description |
|---|---|---|
| `generate_word_image_task` | `queue_core` | Generates AI image -> GCS upload -> WS notify |
| `trigger_image_regeneration_task` | `queue_core` | Deletes old image + regenerates |
| `translate_pure_text_task` | `queue_core` | Chinese -> Vietnamese translation via Gemini AI |
| `process_audio_task` | `queue_paid/free/guest` | Proxies audio to internal AI scoring service |
| `generate_pdf_task` | `queue_core` | Renders vocabulary PDF (Noto Sans CJK fonts) |
| `import_full_exam_task` | `queue_core` | Imports exam metadata & processes audio segments |
| `calculate_daily_streaks` | `queue_core` | Calculates user learning streaks daily |
| `process_expired_subscriptions` | `queue_core` | Handles expired subscription plan downgrades |

---

## Authentication and Security

### Authentication Flow

```
Firebase Client SDK -> Firebase ID Token
        │
        ▼
Next.js BFF (Backend-for-Frontend)
        │ httpOnly Cookie (access_token + refresh_token)
        ▼
Django CookieJWTAuthentication
        │
        ▼
REST Framework Permission Classes
```

### Security Layers

| Layer | Implementation |
|---|---|
| **Auth Provider** | Firebase Authentication (Google, Email) |
| **Token Format** | JWT (SimpleJWT) in httpOnly Secure cookies |
| **CORS** | Explicit origins + Vercel preview regex |
| **CSRF** | Django CSRF middleware |
| **Rate Limiting** | DRF throttles: `anon=20/min`, `user=60/min` |
| **Volume Limiting** | `VolumeLimitMiddleware` - bandwidth limit per tier |
| **HSTS** | 1 year + preload + subdomains |
| **Guest Support** | `X-Guest-ID` header, IDOR protection |

---

## Database Schema

### Core Models

| App | Model | Description |
|---|---|---|
| `dictionary_zh` | `ZhWord` | Chinese words (HSK level, pinyin, Han-Viet, definitions) |
| `dictionary_zh` | `ZhExample` | Chinese example sentences |
| `dictionary_en` | `EnWord` | English words (IPA, frequency rank, part of speech) |
| `dictionary_en` | `EnDefinition` | English definition details |
| `assessments` | `AssessmentTask` | Async pronunciation assessment task |
| `exams` | `Exam`, `ExamQuestion` | HSK/IELTS exam management models |
| `notes` | `Notebook`, `NoteWord` | User notebook and word mappings |
| `media` | `ZhEnMapping` | Cross-language mapping + prompt description |
| `subscriptions` | `SubscriptionPlan` | 4 tiers: Free, Plus, Pro, Premium |
| `subscriptions` | `UserSubscription` | Active user subscriptions |
| `subscriptions` | `PaymentOrder` | SePay automated QR payment order |
| `users` | `CustomUser` | User profile extensions (Firebase UID, avatar, tier) |
| `gamification` | `UserStreak` | Active study streak calendar |
| `notifications` | `Notification` | Push notification persistence with TTL |
| `reports` | `ContentReport`, `SupportRequest` | System bug reporting & customer service tickets |

### Search Optimization

- **GIN Index** on `translation_vi`, `han_viet` (Chinese dictionary search)
- **Trigram Index** (`pg_trgm`) for fuzzy search on Vietnamese definitions
- **Full-text Search Vector** on `ZhExample` and `EnExample`
- **Jieba Tokenization** for Chinese segment search indexing

---

## Integrated Microservices

- **AI English**: `:8000` | FastAPI + ONNX | ONNX FP16 pronunciation scorer + Whisper ASR
- **AI Chinese**: `:8001` | FastAPI + Whisper | Faster-Whisper + custom scoring algorithms
- **TTS**: `:8002` | FastAPI | Edge-TTS neural voices + Google Cloud Storage cache
- **Image**: `:8003` | FastAPI | Imagen 4.0 API + Google Cloud Storage upload
- **PDF**: `:8082` | FastAPI | ReportLab engine + Noto Sans SC font loading
- **WS Gateway**: `:8005` | FastAPI + Redis | WebSocket pub/sub notification router

---

## Caching Strategy

```
Request -> Nginx Cache (static) -> Django View
                                      │
                                      ▼
                               Redis Cache (L1)
                              ┌────────────────────┐
                              │ img:{lang}:{id}     │ -> Image status/URL
                              │ generating:img:...  │ -> Lock flag (5 min TTL)
                              │ dict:zh:search:...  │ -> Search results
                              │ translation:...     │ -> AI translation cache
                              └────────────────────┘
                                      │ Cache Miss
                                      ▼
                               PostgreSQL (L2)
```

---

## Development

```bash
# Run Django dev server (inside Docker)
docker exec -it xiaoyuedict-core-django-1 python manage.py runserver 0.0.0.0:8080

# Apply migrations
docker exec xiaoyuedict-core-django-1 python manage.py migrate

# Create superuser
docker exec -it xiaoyuedict-core-django-1 python manage.py createsuperuser

# Monitor Celery worker logs
docker logs -f xiaoyuedict-celery-worker-core-1

# Open Django shell
docker exec -it xiaoyuedict-core-django-1 python manage.py shell
```

---

## Dependencies

```
django>=4.2                 # Web framework
djangorestframework         # REST API
djangorestframework-simplejwt # JWT auth
celery                      # Task queue
redis                       # Broker + cache
psycopg2-binary             # PostgreSQL driver
gunicorn                    # WSGI server
django-cors-headers         # CORS handling
dj-database-url             # Database URL parsing
firebase-admin              # Firebase Authentication
google-genai                # Gemini AI (translation)
google-cloud-storage        # GCS object storage
google-cloud-aiplatform     # Vertex AI
jieba                       # Chinese text segmentation
pyspellchecker              # Spell checking
Pillow                      # Image processing
PyJWT>=2.8                  # JWT encoding
```

---

<sub>See also: [Frontend README](../frontend_nextjs/README.md)</sub>

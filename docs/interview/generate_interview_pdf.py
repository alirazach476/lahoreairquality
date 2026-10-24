#!/usr/bin/env python3
"""Generate the interview / portfolio PDF for Lahore Air Quality Intelligence Platform."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "Lahore_Air_Quality_Intelligence_Platform_Interview.pdf"
IMAGES = ROOT / "docs" / "images"

ACCENT = colors.HexColor("#0b6e6a")
INK = colors.HexColor("#101820")
MUTED = colors.HexColor("#5a6b7a")
LINE = colors.HexColor("#d0d7de")
SOFT = colors.HexColor("#f4f8fb")


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=ACCENT,
            spaceBefore=14,
            spaceAfter=8,
            borderPadding=2,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "note",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            spaceAfter=8,
            leftIndent=4,
            rightIndent=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=INK,
            spaceAfter=2,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=INK,
            backColor=SOFT,
            leftIndent=4,
            rightIndent=4,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "ph": ParagraphStyle(
            "ph",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#8a6d3b"),
            backColor=colors.HexColor("#fff8e6"),
            borderPadding=6,
            spaceAfter=8,
        ),
    }


def bullets(items: list[str], st) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, st["bullet"]), leftIndent=12, bulletColor=ACCENT) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=10,
        spaceAfter=8,
    )


def code_block(text: str, st) -> Preformatted:
    return Preformatted(text.strip("\n"), st["code"], maxLineLength=95)


def simple_table(rows: list[list[str]], col_widths: list[float] | None = None) -> Table:
    data = [[Paragraph(str(c), ParagraphStyle("td", fontName="Helvetica", fontSize=8, leading=10, textColor=INK)) for c in row] for row in rows]
    # Bold header
    data[0] = [
        Paragraph(str(c), ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white))
        for c in rows[0]
    ]
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def placeholder_box(text: str, st) -> Paragraph:
    return Paragraph(f"<b>Placeholder (not a measured result):</b> {text}", st["ph"])


def add_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 12 * mm, A4[0] - 18 * mm, A4[1] - 12 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, A4[1] - 10 * mm, "Lahore Air Quality Intelligence Platform — Interview Brief")
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.drawCentredString(A4[0] / 2, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    st = styles()
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Lahore Air Quality Intelligence Platform — Interview Brief",
        author="Ali Raza Chaudhry",
    )
    story: list = []
    W = A4[0] - 36 * mm

    # ----- Cover -----
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph("Lahore Air Quality Intelligence Platform", st["cover_title"]))
    story.append(Paragraph("Interview &amp; Portfolio Engineering Brief", st["cover_sub"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("End-to-end air-quality data platform for Lahore, Pakistan", st["cover_sub"]))
    story.append(Paragraph("Ingestion · Warehouse · AQI · Forecasting · API · Dashboard", st["cover_sub"]))
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            "Live dashboard: <link href='https://lahoreairquality.vercel.app' color='#0b6e6a'>"
            "https://lahoreairquality.vercel.app</link>",
            st["cover_sub"],
        )
    )
    story.append(
        Paragraph(
            "Source: <link href='https://github.com/alirazach476/lahoreairquality' color='#0b6e6a'>"
            "github.com/alirazach476/lahoreairquality</link>",
            st["cover_sub"],
        )
    )
    story.append(Spacer(1, 20 * mm))
    story.append(
        Paragraph(
            "This document describes implemented system behaviour and reproducible commands. "
            "Operational volume statistics that are not yet measured appear only as labelled placeholders. "
            "Model metrics below are taken from written evaluation artifacts in the repository "
            "(not invented for this brief).",
            st["note"],
        )
    )
    story.append(PageBreak())

    # 1 Overview
    story.append(Paragraph("1. Project overview", st["h1"]))
    story.append(
        Paragraph(
            "The Lahore Air Quality Intelligence Platform is a production-style portfolio system that "
            "continuously collects Lahore air-quality and weather observations, archives raw payloads, "
            "loads a PostgreSQL warehouse, transforms data with dbt, calculates United States EPA Air "
            "Quality Index (AQI) values, trains and serves short-horizon forecasts, and exposes results "
            "through a FastAPI service and a React dashboard.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Internal storage and computation use <b>UTC</b>. User-facing timestamps are displayed in "
            "<b>Asia/Karachi (PKT)</b>. The platform does not fabricate sensor readings or API responses.",
            st["body"],
        )
    )

    # 2 Problem
    story.append(Paragraph("2. Problem statement", st["h1"]))
    story.append(
        Paragraph(
            "Lahore experiences episodic severe particulate pollution. Reliable decision support requires "
            "more than a single public widget: raw feeds must be archived, quality-checked, joined with "
            "weather context, converted to a documented AQI standard, and forecasted with reproducible "
            "training and evaluation. Upstream monitors (for example AirNow via OpenAQ) already report "
            "US EPA AQI; this platform aligns calculation and serving to that standard while making "
            "ingestion failures, stale data, and model provenance explicit.",
            st["body"],
        )
    )
    story.append(bullets([
        "Unify discovery and polling of OpenAQ monitors near Lahore with Open-Meteo weather.",
        "Guarantee raw archive + warehouse durability without silent data loss.",
        "Classify quality issues instead of deleting source rows.",
        "Serve current AQI, history, forecasts, sensors, and quality status via a documented API and UI.",
    ], st))

    # 3 Features
    story.append(Paragraph("3. Key features", st["h1"]))
    story.append(bullets([
        "Runtime discovery of OpenAQ locations near configurable Lahore coordinates (no hard-coded station IDs).",
        "Kafka-compatible streaming (Redpanda) between poller and consumer with idempotent sinks.",
        "Dual-write path: object store (raw JSON) then PostgreSQL upserts.",
        "dbt staging → intermediate → marts, including AQI sub-index and feature marts.",
        "US EPA AQI from shared Python + dbt breakpoint tables (Feb 2024 PM2.5 breakpoints).",
        "Chronological ML evaluation with naive / seasonal-naive baselines, SARIMA, and XGBoost.",
        "MLflow experiment tracking for training runs.",
        "Dagster orchestration of pipeline assets and schedules.",
        "FastAPI with OpenAPI docs; React dashboard (Vercel-hosted frontend).",
        "Documented failure simulations for ten dependency / data-path scenarios.",
    ], st))

    # 4 Architecture
    story.append(Paragraph("4. Architecture", st["h1"]))
    story.append(code_block(
        """
External APIs (OpenAQ v3, Open-Meteo)
  → ingestion/poller → Redpanda topics (aq.raw, weather.raw)
  → ingestion/consumer → object store (raw JSON) + PostgreSQL (raw)
  → dbt (staging → intermediate → marts; quality classify + report)
  → ml (features → train / infer; MLflow tracking)
  → apps/api (FastAPI) → apps/dashboard (React)
Dagster schedules and observes assets; it does not replace domain packages.
""",
        st,
    ))
    story.append(
        Paragraph(
            "Design emphasis: partial failure isolation (AQ and weather poll independently), "
            "at-least-once delivery with idempotent sinks, S3-before-Postgres ordering, and "
            "observability of stale / missing / delayed data rather than silent imputation.",
            st["body"],
        )
    )

    # 5 Tech stack
    story.append(Paragraph("5. Tech stack", st["h1"]))
    story.append(
        simple_table(
            [
                ["Layer", "Technology"],
                ["Ingestion", "Python poller &amp; consumer; Redpanda (Kafka API)"],
                ["Archive", "S3-compatible object storage (Adobe S3Mock locally)"],
                ["Warehouse", "PostgreSQL + Alembic migrations"],
                ["Transforms", "dbt"],
                ["Orchestration", "Dagster"],
                ["ML / tracking", "XGBoost, SARIMA (statsmodels), MLflow"],
                ["API", "FastAPI (OpenAPI)"],
                ["Dashboard", "React 19 + Vite + TypeScript"],
                ["Local runtime", "Docker Compose"],
                ["CI", "GitHub Actions"],
                ["Frontend host", "Vercel (static dashboard)"],
            ],
            [38 * mm, W - 38 * mm],
        )
    )
    story.append(Spacer(1, 4 * mm))

    # 6 Data sources
    story.append(Paragraph("6. Data sources", st["h1"]))
    story.append(Paragraph("<b>Air quality — OpenAQ API v3</b>", st["h2"]))
    story.append(bullets([
        "Base URL via <font face='Courier'>OPENAQ_BASE_URL</font> (default https://api.openaq.org).",
        "Auth: header <font face='Courier'>X-API-Key</font> from <font face='Courier'>OPENAQ_API_KEY</font>.",
        "Discover monitors: <font face='Courier'>GET /v3/locations</font> with Lahore coordinates, radius, ISO=PK.",
        "Latest / historical measurements via location and sensor endpoints.",
        "Published free-tier rate limits (OpenAQ docs): 60 requests/min, 2,000/hour — subject to provider policy.",
    ], st))
    story.append(Paragraph("<b>Weather — Open-Meteo</b>", st["h2"]))
    story.append(bullets([
        "Forecast/current: <font face='Courier'>OPENMETEO_BASE_URL</font>; archive: <font face='Courier'>OPENMETEO_ARCHIVE_BASE_URL</font>.",
        "No API key required for public endpoints used here.",
        "ML weather variables: temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m (m/s), wind_direction_10m, surface_pressure.",
    ], st))
    story.append(placeholder_box(
        "After sustained production polling, report approximate volume as "
        "<b>~X readings/day</b> across <b>~N sensors</b> over <b>~Y months</b>. "
        "Do not substitute invented integers here.",
        st,
    ))

    # 7 Pipeline
    story.append(Paragraph("7. Data pipeline", st["h1"]))
    story.append(bullets([
        "<b>Poll:</b> scheduled OpenAQ + Open-Meteo fetches; publish normalized envelopes to Redpanda.",
        "<b>Consume:</b> validate → write deterministic object-store key → Postgres upsert → commit offset.",
        "<b>Transform:</b> dbt staging, intermediate (dedupe, normalize, AQI sub-index, weather join), marts.",
        "<b>Quality:</b> classify valid / suspect / invalid; retain rows; roll up report mart.",
        "<b>Features / train:</b> causal feature dataset; chronological splits; train SARIMA / XGBoost.",
        "<b>Serve:</b> FastAPI reads marts / forecast tables; dashboard polls JSON endpoints.",
    ], st))
    story.append(code_block(
        """
# Full local stack
cp .env.example .env
docker compose up -d --build

# dbt (Compose tooling profile)
make compose-dbt && make compose-dbt-test

# Optional history bootstrap (real providers; requires keys / network)
# see docs/bootstrap-history.md
""",
        st,
    ))

    # 8 Data quality
    story.append(Paragraph("8. Data quality", st["h1"]))
    story.append(
        Paragraph(
            "Suspicious and invalid observations are <b>classified and retained</b>. The platform never "
            "automatically deletes source rows based on quality rules. Disposition classes: "
            "<b>valid</b> | <b>suspect</b> | <b>invalid</b>.",
            st["body"],
        )
    )
    story.append(
        simple_table(
            [
                ["Example rule", "Severity", "Condition (summary)"],
                ["missing_timestamp", "invalid", "observed_at is null"],
                ["missing_value", "invalid", "concentration missing / non-numeric"],
                ["future_timestamp", "invalid / suspect", "beyond UTC now (+1h invalid; +5m–1h suspect)"],
                ["unexpected_unit", "invalid", "unit not allowed for pollutant"],
                ["negative_concentration", "invalid", "value &lt; 0"],
                ["duplicate_observation", "suspect", "natural key already present (row kept)"],
                ["delayed_ingest", "suspect", "ingested_at − observed_at &gt; 6 hours"],
                ["missing_weather", "suspect", "no weather row for same UTC hour"],
            ],
            [42 * mm, 28 * mm, W - 70 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(code_block(
        """
python -m lahore_air_quality.quality
python -m lahore_air_quality.quality --json
# API: GET /api/data-quality
""",
        st,
    ))

    # 9 AQI
    story.append(Paragraph("9. AQI methodology", st["h1"]))
    story.append(
        Paragraph(
            "Standard: <b>US EPA Air Quality Index</b> (40 CFR Part 58 Appendix G; EPA February 2024 "
            "PM2.5 breakpoint update effective 6 May 2024; AirNow TAD truncation rules). Breakpoints are "
            "copied from EPA tables into Python (<font face='Courier'>src/lahore_air_quality/aqi/</font>) "
            "and the dbt seed <font face='Courier'>aqi_breakpoints.csv</font> — never invented in code.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Rationale for Lahore portfolio use: primary OpenAQ coverage used in development (e.g. AirNow "
            "feeds) reports US EPA AQI. This is a documented engineering choice for consistency with "
            "upstream monitors, not a claim that EPA AQI is Pakistan’s official national index.",
            st["body"],
        )
    )
    story.append(bullets([
        "Concentrations are truncated (not rounded) per EPA TAD before breakpoint lookup.",
        "If the source unit does not match the EPA table unit for that pollutant, no AQI is calculated for that reading (no invented unit conversion).",
        "Overall AQI is the maximum sub-index among pollutants that could be scored.",
    ], st))

    # 10 ML
    story.append(Paragraph("10. Machine learning", st["h1"]))
    story.append(
        Paragraph(
            "Forecasting targets short-horizon PM2.5 / AQI-related labels on a causal feature dataset "
            "(lags, rolling statistics, weather, calendar). Splits are chronological (default 70% / 15% / 15%); "
            "series are never randomly shuffled. Feature construction forbids future leakage into training rows.",
            st["body"],
        )
    )
    story.append(code_block(
        """
pip install -e "./ml[dev]"
python ml/training/train_xgboost.py \\
  --from-features ml/features/datasets/lahore_aqi_features.parquet \\
  --output-dir ml/training/artifacts/xgboost \\
  --run-name xgboost -v
""",
        st,
    ))

    # 11 Model comparison
    story.append(Paragraph("11. Model comparison", st["h1"]))
    story.append(
        Paragraph(
            "The evaluation package scores MAE, RMSE, and MAPE (MAPE excludes near-zero actuals). "
            "Baselines: naive last value and seasonal naive (default season 24 for hourly). "
            "The table below is copied from the repository artifact "
            "<font face='Courier'>ml/training/artifacts/xgboost/xgboost_metrics.md</font> "
            "(target <font face='Courier'>target_pm25_lead_1</font>, horizon 1, <b>test</b> split). "
            "These figures reflect that artifact’s measured rows (<b>n_obs = 35</b> for XGBoost/naive; "
            "34 for SARIMA reference) — not invented interview numbers. Scope is limited to the feature "
            "dataset used for that run; do not generalise as city-wide production accuracy without "
            "re-evaluating on a longer live window.",
            st["body"],
        )
    )
    story.append(
        simple_table(
            [
                ["Model", "MAE", "RMSE", "MAPE (fraction)", "n_obs"],
                ["xgboost_h1", "2.8099", "3.2844", "0.1450 (~14.5%)", "35"],
                ["naive_last_value_h1", "6.0179", "7.0237", "0.2573", "35"],
                ["seasonal_naive_s24", "3.4664", "4.1134", "0.1797", "35"],
                ["sarima_reference", "4.1800", "4.9832", "0.1955", "34"],
            ],
            [45 * mm, 25 * mm, 25 * mm, 40 * mm, 20 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(placeholder_box(
        "For a future production scorecard over a longer window, report test MAPE as "
        "<b>Z% MAPE</b> with explicit n_obs, date range (~Y months), and sensor coverage (~N sensors).",
        st,
    ))

    # 12 API
    story.append(Paragraph("12. API", st["h1"]))
    story.append(
        simple_table(
            [
                ["Method", "Path", "Purpose"],
                ["GET", "/health", "Liveness + database probe"],
                ["GET", "/api/air-quality/current", "Latest city/station AQI + weather + freshness"],
                ["GET", "/api/air-quality/history", "Historical points (hours window)"],
                ["GET", "/api/forecast", "Published model forecasts"],
                ["GET", "/api/sensors", "Station inventory"],
                ["GET", "/api/data-quality", "Quality snapshot"],
                ["GET", "/resilience/scenarios", "Failure-scenario catalog"],
                ["GET", "/resilience/status", "Live resilience probes"],
            ],
            [22 * mm, 58 * mm, W - 80 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(code_block(
        """
pip install -e "./apps/api[dev]"
lahore-aqi-api
# OpenAPI UI: http://localhost:8000/docs
""",
        st,
    ))

    # 13 Dashboard
    story.append(Paragraph("13. Dashboard", st["h1"]))
    story.append(
        Paragraph(
            "React dashboard consumes only the public FastAPI origin (<font face='Courier'>VITE_API_BASE_URL</font>). "
            "UI includes an AQI gauge, Lahore time/place card, PM2.5 and weather metrics (PM10 omitted from UI), "
            "history (AQI / PM2.5 toggle), 24–48h forecast chart, pollutant bars, and sensors / quality panels. "
            "Empty, loading, network, and stale states are handled per panel.",
            st["body"],
        )
    )
    story.append(code_block(
        """
cd apps/dashboard
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm install && npm run dev
# Production static host: https://lahoreairquality.vercel.app
""",
        st,
    ))

    # 14 Local setup
    story.append(Paragraph("14. Local setup", st["h1"]))
    story.append(Paragraph("<b>Prerequisites:</b> Docker Engine + Compose v2; Node 22+ for Vite-only frontend work; Python 3.12+ for host tooling.", st["body"]))
    story.append(code_block(
        """
git clone https://github.com/alirazach476/lahoreairquality.git
cd lahoreairquality
cp .env.example .env
# Set OPENAQ_API_KEY for live air-quality polling

docker compose up -d --build
docker compose ps
docker compose logs -f api

# Host Python (optional)
pip install -e ".[dev]"
pip install -e apps/api -e ingestion/poller -e ingestion/consumer -e ml -e orchestration/dagster
""",
        st,
    ))
    story.append(
        simple_table(
            [
                ["Service", "URL"],
                ["Dashboard", "http://localhost:8080"],
                ["API / OpenAPI", "http://localhost:8000/docs"],
                ["Dagster", "http://localhost:3000"],
                ["MLflow", "http://localhost:5000"],
            ],
            [40 * mm, W - 40 * mm],
        )
    )

    # 15 Env vars
    story.append(Paragraph("15. Environment variables", st["h1"]))
    story.append(
        Paragraph(
            "Copy <font face='Courier'>.env.example</font> → <font face='Courier'>.env</font>. "
            "Never commit secrets. Compose injects container service hostnames; host tools keep localhost.",
            st["body"],
        )
    )
    story.append(
        simple_table(
            [
                ["Variable", "Role"],
                ["OPENAQ_API_KEY", "OpenAQ v3 authentication"],
                ["OPENAQ_BASE_URL / OPENMETEO_*", "Provider hosts"],
                ["LAHORE_LATITUDE / LONGITUDE", "Discovery centre (WGS84)"],
                ["POLL_INTERVAL_SECONDS", "Poller cadence (default 300)"],
                ["POSTGRES_*", "Warehouse connection"],
                ["REDPANDA_BROKERS / topics", "Kafka-compatible broker + topics"],
                ["S3_ENDPOINT_URL / S3_BUCKET / AWS_*", "Object-store archive"],
                ["MLFLOW_TRACKING_URI", "Experiment tracking URI"],
                ["API_CORS_ORIGINS", "Allowed browser origins"],
                ["VITE_API_BASE_URL", "Dashboard build-time API origin"],
            ],
            [55 * mm, W - 55 * mm],
        )
    )

    # 16 Docker
    story.append(Paragraph("16. Docker setup", st["h1"]))
    story.append(code_block(
        """
docker compose up -d --build          # or: make compose-up
docker compose down                   # keep volumes
docker compose down -v                # wipe volumes
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose --profile tools run --rm test
docker compose --profile tools run --rm dbt
make compose-train-synthetic          # XGBoost → MLflow (Compose tooling)
""",
        st,
    ))
    story.append(
        Paragraph(
            "App images run as non-root (uid 10001) where practical. Health checks gate "
            "<font face='Courier'>depends_on</font> for Postgres, Redpanda, API, dashboard, Dagster, and MLflow.",
            st["body"],
        )
    )

    # 17 Testing
    story.append(Paragraph("17. Testing", st["h1"]))
    story.append(code_block(
        """
# Default suite — mocked HTTP; no live provider credentials required
pip install -e ".[dev]" -e "ingestion/poller" -e "ingestion/consumer" -e "apps/api"
pytest
# or: make test

pytest tests/resilience -v            # failure simulations
# or: make test-resilience

RUN_EXTERNAL_API_TESTS=1 make test-integration   # opt-in live APIs
make smoke                            # e2e ingestion with mocked providers
""",
        st,
    ))
    story.append(
        Paragraph(
            "External client scenario tests cover success, empty, invalid, HTTP failure, rate-limit, "
            "timeout, and retry behaviour for OpenAQ and Open-Meteo under mocks.",
            st["body"],
        )
    )

    # 18 MLflow
    story.append(Paragraph("18. MLflow", st["h1"]))
    story.append(bullets([
        "Tracking URI resolution: CLI → <font face='Courier'>MLFLOW_TRACKING_URI</font> → local <font face='Courier'>./mlruns</font>.",
        "Experiments: <font face='Courier'>lahore-aqi/xgboost</font>, <font face='Courier'>lahore-aqi/sarima</font>.",
        "Logged: parameters, MAE/RMSE/MAPE, training duration, model + prediction + metric artifacts.",
        "Disable per run with <font face='Courier'>--no-mlflow</font>.",
        "UI via Compose: http://localhost:5000",
    ], st))

    # 19 Failure handling
    story.append(Paragraph("19. Failure handling", st["h1"]))
    story.append(
        Paragraph(
            "Principles: detect (typed errors, health probes), log structured events, retry when appropriate, "
            "never invent observations, recover on the next successful cycle / Kafka redelivery, expose status "
            "via metrics and HTTP. There is no dead-letter topic today: poison messages are rejected with "
            "offset commit; retryable sink failures hold the offset.",
            st["body"],
        )
    )
    story.append(
        simple_table(
            [
                ["#", "Scenario", "Core behaviour"],
                ["1", "OpenAQ unavailable", "AQ leg fails; Open-Meteo continues; next poll retries"],
                ["2", "Open-Meteo unavailable", "Symmetric isolation for weather leg"],
                ["3", "Redpanda unavailable", "No unpublished sink writes; producer/consumer retries"],
                ["4", "PostgreSQL unavailable", "Offset held; S3 may already hold payload; API /health 503"],
                ["5", "Object store unavailable", "No Postgres write without archive; offset held"],
                ["6", "Malformed event", "Reject + commit (no fake readings)"],
                ["7", "Duplicate event", "Idempotent upsert / deterministic S3 key"],
                ["8", "Stale sensor", "Observability flags; freshness on API"],
                ["9", "Missing readings", "Empty poll logged; gaps reported; no zero-imputation"],
                ["10", "Delayed event", "suspect delayed_ingest; row retained"],
            ],
            [10 * mm, 42 * mm, W - 52 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Details: <font face='Courier'>docs/failure-recovery.md</font>.", st["note"]))

    # 20 Structure
    story.append(Paragraph("20. Project structure", st["h1"]))
    story.append(code_block(
        """
apps/            FastAPI + React dashboard
data/            Local raw/processed placeholders
dbt/             Warehouse transforms and tests
ingestion/       Poller (produce) + consumer (archive + load)
ml/              Features, training, evaluation, inference
orchestration/   Dagster assets, jobs, schedules
infrastructure/  Dockerfiles, nginx, Postgres init
tests/           Unit / integration / resilience / smoke
docs/            Architecture, runbooks, interview PDF
scripts/         Dev utilities (e.g. seed_demo_forecasts)
src/             Shared AQI, DB, quality, resilience libraries
""",
        st,
    ))

    # 21 Screenshots
    story.append(Paragraph("21. Screenshots", st["h1"]))
    story.append(
        Paragraph(
            "Replace or supplement the placeholders below with current captures from the running dashboard "
            "(local <font face='Courier'>http://localhost:8080</font> or "
            "<link href='https://lahoreairquality.vercel.app' color='#0b6e6a'>lahoreairquality.vercel.app</link>). "
            "Repository images live under <font face='Courier'>docs/images/</font>.",
            st["body"],
        )
    )

    from reportlab.platypus import Image as RLImage

    def try_image(path: Path, caption: str, max_w: float = W, max_h: float = 85 * mm):
        if not path.exists():
            story.append(placeholder_box(f"[Screenshot placeholder] {caption} — file missing: {path.name}", st))
            return
        img = RLImage(str(path))
        iw, ih = img.imageWidth, img.imageHeight
        scale = min(max_w / iw, max_h / ih)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        story.append(KeepTogether([img, Paragraph(caption, st["caption"])]))

    try_image(IMAGES / "dashboard-hero.png", "Figure 1. Dashboard hero — AQI gauge, Lahore time/place, freshness.")
    try_image(IMAGES / "dashboard-charts.png", "Figure 2. Historical trend and 24–48h forecast charts.")
    story.append(placeholder_box(
        "[Optional] Figure 3. MLflow UI experiment run · "
        "[Optional] Figure 4. Dagster asset graph · "
        "[Optional] Figure 5. OpenAPI /docs screenshot",
        st,
    ))

    # 22 Future
    story.append(Paragraph("22. Future improvements", st["h1"]))
    story.append(bullets([
        "Host FastAPI + warehouse on a durable public backend so the Vercel UI always has a stable API origin.",
        "Named Cloudflare / reverse-proxy tunnel or cloud deployment instead of ephemeral quick tunnels.",
        "Dead-letter topic for poison messages with operator replay tooling.",
        "Longer live evaluation windows and station-level models with published scorecards.",
        "Optional unit conversion layer (documented) where OpenAQ units differ from EPA tables.",
        "Alerting on stale sensors and quality-class spikes.",
    ], st))

    # 23 Limitations
    story.append(Paragraph("23. Limitations", st["h1"]))
    story.append(bullets([
        "Vercel hosts the static dashboard only; live charts require a reachable FastAPI backend and CORS allow-list.",
        "AQI is not calculated when upstream units do not match EPA table units (no silent conversion).",
        "XGBoost metrics above are from a finite feature-artifact test set (n_obs ≈ 35); not a multi-year citywide claim.",
        "No DLQ yet; rejected poison events are logged and committed.",
        "Local object store uses S3Mock in Compose — behaviour may differ from production S3/MinIO.",
        "Operational throughput (~X readings/day, ~N sensors, ~Y months) should be measured from warehouse queries before citing in interviews.",
    ], st))

    # 24 Author
    story.append(Paragraph("24. Author", st["h1"]))
    story.append(
        Paragraph(
            "<b>Ali Raza Chaudhry</b><br/>"
            "GitHub: <link href='https://github.com/alirazach476' color='#0b6e6a'>github.com/alirazach476</link><br/>"
            "Repository: <link href='https://github.com/alirazach476/lahoreairquality' color='#0b6e6a'>"
            "github.com/alirazach476/lahoreairquality</link><br/>"
            "Live dashboard: <link href='https://lahoreairquality.vercel.app' color='#0b6e6a'>"
            "lahoreairquality.vercel.app</link>",
            st["body"],
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Document generated from repository documentation and measured ML artifacts. "
            "Regenerate with: <font face='Courier'>python docs/interview/generate_interview_pdf.py</font>",
            st["note"],
        )
    )

    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()

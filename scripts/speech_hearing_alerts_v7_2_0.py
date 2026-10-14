#!/usr/bin/env python3

"""
ISHA PROFESSIONAL INTELLIGENCE V7.2.0

Speech • Language • Hearing • Communication

Designed for Indian SLP/Audiology professionals.

PIPELINES
---------
1. Clinical / Research / Policy / Technology news
2. Upcoming national/international conferences >=90 days away
3. Government Audiology / SLP vacancies open NOW

DESIGN PRINCIPLES
-----------------
- Prefer recent developments over static resources
- Prefer official professional sources
- Include Indian developments first when equally relevant
- Support Audiology + full SLP scope
- Deduplicate syndicated/repeated stories
- Never classify a generic resource page as a job
- Never classify a static practice portal as news
- Require evidence for open government vacancies
- Preserve/migrate existing SQLite memory
- Never allow source-health database errors to crash workflow
"""

from __future__ import annotations

import os
import re
import sqlite3
import hashlib
import difflib
import io
import warnings
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from pypdf import PdfReader

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from dateutil import parser as dtparser
from zoneinfo import ZoneInfo


# ============================================================
# BASIC SETTINGS
# ============================================================

warnings.filterwarnings(
    "ignore",
    category=MarkupResemblesLocatorWarning,
)

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
AUDIT_DIR = ROOT / "audit"

DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "feeds_v7_2_0.yaml"

DATABASE = DATA_DIR / "alert_memory.sqlite"

IST = ZoneInfo("Asia/Kolkata")

NEWS_DAYS = 7
MEMORY_DAYS = 30

MAX_NEWS = 15
MAX_CONFERENCES = 8
MAX_JOBS = None  # No arbitrary cap: include every verified open vacancy found.

MIN_CONFERENCE_DAYS = 90

TIMEOUT = 25

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 "
        "(compatible; ISHA-Professional-"
        "Intelligence/7.2.0)"
}


# ============================================================
# PROFESSIONAL TOPICS
# ============================================================

TOPICS = {

    "Audiology": [
        "audiology",
        "audiologist",
        "hearing loss",
        "hearing aid",
        "hearing aids",
        "hearing device",
        "hearing technology",
        "hearing rehabilitation",
        "audiological",
        "auditory",
    ],

    "Cochlear Implant": [
        "cochlear implant",
        "cochlear implants",
        "cochlear implantation",
        "auditory implant",
        "implantable hearing",
    ],

    "Vestibular": [
        "vestibular",
        "vertigo",
        "dizziness",
        "balance disorder",
        "bppv",
        "vestibular migraine",
        "vestibular rehabilitation",
        "pppd",
        "persistent postural perceptual dizziness",
    ],

    "Tinnitus": [
        "tinnitus",
        "hyperacusis",
        "misophonia",
    ],

    "Stuttering / Fluency": [
        "stuttering",
        "stutter",
        "stammering",
        "stammer",
        "cluttering",
        "fluency disorder",
        "fluency",
    ],

    "Speech Sound Disorders": [
        "articulation disorder",
        "articulation disorders",
        "speech sound disorder",
        "speech-sound disorder",
        "phonological disorder",
        "phonology",
        "speech intelligibility",
    ],

    "Apraxia / Motor Speech": [
        "apraxia",
        "childhood apraxia",
        "motor speech",
        "acquired apraxia",
    ],

    "Dysarthria": [
        "dysarthria",
        "dysarthric",
    ],

    "Aphasia": [
        "aphasia",
        "aphasic",
        "language rehabilitation",
        "post-stroke language",
    ],

    "Developmental Language": [
        "developmental language disorder",
        "developmental language",
        "language disorder",
        "language delay",
        "dld",
    ],

    "Cleft / Craniofacial": [
        "cleft palate",
        "cleft lip",
        "cleft lip and palate",
        "craniofacial",
        "velopharyngeal",
        "velopharyngeal dysfunction",
        "hypernasality",
        "hyponasality",
    ],

    "Voice": [
        "voice disorder",
        "dysphonia",
        "vocal fold",
        "vocal folds",
        "vocal cord",
        "laryng",
        "voice therapy",
    ],

    "Dysphagia / Feeding": [
        "dysphagia",
        "swallowing",
        "swallow disorder",
        "feeding disorder",
        "pediatric feeding",
        "aspiration",
        "fees",
        "vfss",
        "videofluoroscopic swallow",
        "iddsi",
    ],

    "AAC": [
        "augmentative and alternative communication",
        "augmentative communication",
        "alternative communication",
        "aac",
        "speech generating device",
        "communication device",
    ],

    "Neurogenic Communication": [
        "stroke",
        "traumatic brain injury",
        "tbi",
        "parkinson",
        "parkinson's",
        "als",
        "dementia",
        "multiple sclerosis",
        "neurogenic communication",
    ],

    "Autism / Social Communication": [
        "autism",
        "autism spectrum",
        "social communication",
        "pragmatic language",
    ],

    "Orofacial Myofunctional": [
        "orofacial myofunctional",
        "orofacial myofunctional disorder",
        "omd",
        "ankyloglossia",
        "tongue tie",
    ],

    "Head & Neck": [
        "head and neck cancer",
        "head and neck rehabilitation",
        "laryngectomy",
        "alaryngeal",
        "tracheostomy",
    ],

    "Research / AI / Technology": [
        "clinical trial",
        "clinical research",
        "artificial intelligence",
        "machine learning",
        "digital health",
        "telepractice",
        "telehealth",
        "speech technology",
        "wearable",
        "diagnostic technology",
    ],

    "Professional Policy": [
        "scope of practice",
        "professional standard",
        "clinical guideline",
        "practice guideline",
        "position statement",
        "reimbursement",
        "medicare",
        "medicaid",
        "coding",
        "cpt",
        "regulation",
        "licensure",
        "policy",
    ],
}


# ============================================================
# LOW-VALUE / STATIC CONTENT
# ============================================================

STATIC_PATTERNS = [
    "/practice-portal/",
    "/practiceportal/",
    "/consumers/",
    "/consumer/",
    "/membership/",
    "/about/",
    "/education/",
    "/resources/",
    "/products/",
    "/services/",
    "/departments/",
    "/department/",
    "/clinical-topics/",
]

LOW_VALUE = [
    "membership",
    "member benefits",
    "registration fee",
    "exhibitor",
    "exhibit hall",
    "sponsor",
    "sponsorship",
    "hotel",
    "travel package",
    "podcast",
    "webinar registration",
    "course registration",
    "ceu",
    "continuing education course",
    "patient handout",
    "patient information",
    "consumer guide",
    "consumer information",
    "shop",
    "buy now",
]


HIGH_VALUE = [
    "guideline",
    "clinical practice guideline",
    "consensus",
    "systematic review",
    "meta-analysis",
    "clinical trial",
    "randomized",
    "diagnostic",
    "treatment",
    "therapy",
    "intervention",
    "approval",
    "regulation",
    "policy",
    "reimbursement",
    "medicare",
    "government",
    "notification",
    "standard",
    "recommendation",
    "research",
    "study",
    "technology",
    "artificial intelligence",
    "machine learning",
    "device",
    "cpt",
    "coding",
    "position statement",
    "public consultation",
]


# ============================================================
# JOB TERMS
# ============================================================

JOB_TERMS = [
    "audiologist", "audiologist grade", "audiology grade",
    "audiology officer", "audiology technician",
    "speech therapist", "speech-language pathologist",
    "speech language pathologist", "speech and language therapist",
    "speech-language therapist", "speech and hearing technician",
    "audiologist and speech therapist", "audiologist & speech therapist",
    "audiologist cum speech therapist", "slp grade",
]

JOB_QUALIFICATION_TERMS = [
    "baslp", "b.aslp", "b a slp", "bachelor in audiology",
    "bachelor of audiology", "bachelor in audiology speech language pathology",
    "maslp", "m.aslp", "m a slp", "m.sc audiology", "msc audiology",
    "m.sc speech language pathology", "msc speech language pathology",
    "master in audiology", "master of audiology",
    "bachelor of speech and hearing", "audiology and speech language pathology",
]

JOB_SIGNALS = [
    "recruitment", "recruiting", "vacancy", "vacancies", "apply",
    "application", "appointment", "walk-in", "walk in", "last date",
    "closing date", "deadline", "applications invited", "online application",
    "eligible candidates", "applications are invited", "advertisement",
    "employment notice", "recruitment notice", "notification", "careers",
]
JOB_EXCLUDE = [
    "result", "results", "admission", "course", "training", "internship",
    "volunteer", "scope of practice", "syllabus", "curriculum",
    "answer key", "answer keys", "provisional selection list",
    "selected candidates", "waitlist", "waitlisted candidates",
]


# ============================================================
# TIME
# ============================================================

def now_ist():
    return datetime.now(IST)


def today():
    return now_ist().date()


# ============================================================
# TEXT
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    if re.match(
        r"^https?://",
        value.strip(),
        re.I,
    ):
        return value.strip()

    soup = BeautifulSoup(
        value,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def normalize(value):

    text = clean_text(value).lower()

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def hash_key(value):

    return hashlib.sha256(
        normalize(value).encode(
            "utf-8"
        )
    ).hexdigest()[:32]


# ============================================================
# DATE
# ============================================================

def parse_date(value):

    if not value:
        return None

    try:
        parsed = dtparser.parse(
            str(value),            fuzzy=True,            dayfirst=True,        )
        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=IST
            )

        return parsed.astimezone(IST)

    except Exception:

        return None


def extract_date(text):

    patterns = [

        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+20\d{2}\b",

        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2}\b",

        r"\b20\d{2}-\d{1,2}-\d{1,2}\b",

        r"\b\d{1,2}/\d{1,2}/20\d{2}\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text or "",
            re.I,
        )

        if match:

            parsed = parse_date(
                match.group(0)
            )

            if parsed:

                return parsed

    return None


# ============================================================
# HTTP
# ============================================================

def fetch(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# DATABASE
# ============================================================

def init_database():

    con = sqlite3.connect(
        DATABASE
    )

    try:

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                key TEXT PRIMARY KEY,
                kind TEXT,
                title TEXT,
                url TEXT,
                first_seen TEXT,
                last_seen TEXT,
                last_alerted TEXT
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health (
                source TEXT PRIMARY KEY,
                checked_at TEXT,
                checked TEXT,
                ok INTEGER,
                count INTEGER,
                error TEXT
            )
            """
        )

        # ----------------------------------------------------
        # Safe migration
        # ----------------------------------------------------

        seen_columns = {
            row[1]
            for row in con.execute(
                "PRAGMA table_info(seen)"
            )
        }

        for column in [
            "kind",
            "title",
            "url",
            "first_seen",
            "last_seen",
            "last_alerted",
        ]:

            if column not in seen_columns:

                con.execute(
                    f"""
                    ALTER TABLE seen
                    ADD COLUMN {column} TEXT
                    """
                )

        source_columns = {
            row[1]
            for row in con.execute(
                "PRAGMA table_info(source_health)"
            )
        }

        for column, datatype in [
            ("checked_at", "TEXT"),
            ("checked", "TEXT"),
            ("ok", "INTEGER"),
            ("count", "INTEGER"),
            ("error", "TEXT"),
        ]:

            if column not in source_columns:

                con.execute(
                    f"""
                    ALTER TABLE source_health
                    ADD COLUMN {column} {datatype}
                    """
                )

        # Synchronize legacy/current timestamp fields
        con.execute(
            """
            UPDATE source_health
            SET checked_at = checked
            WHERE checked_at IS NULL
            AND checked IS NOT NULL
            """
        )

        con.execute(
            """
            UPDATE source_health
            SET checked = checked_at
            WHERE checked IS NULL
            AND checked_at IS NOT NULL
            """
        )

        con.commit()

    finally:

        con.close()


def was_seen(key):

    con = sqlite3.connect(
        DATABASE
    )

    try:

        row = con.execute(
            """
            SELECT last_alerted
            FROM seen
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

    finally:

        con.close()

    if not row or not row[0]:

        return False

    parsed = parse_date(
        row[0]
    )

    if not parsed:

        return False

    return (
        now_ist() - parsed
        <
        timedelta(
            days=MEMORY_DAYS
        )
    )


def remember(
    key,
    kind,
    title,
    url,
):

    timestamp = now_ist().isoformat()

    con = sqlite3.connect(
        DATABASE
    )

    try:

        con.execute(
            """
            INSERT INTO seen
            (
                key,
                kind,
                title,
                url,
                first_seen,
                last_seen,
                last_alerted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                kind=excluded.kind,
                title=excluded.title,
                url=excluded.url,
                last_seen=excluded.last_seen,
                last_alerted=excluded.last_alerted
            """,
            (
                key,
                kind,
                title,
                url,
                timestamp,
                timestamp,
                timestamp,
            ),
        )

        con.commit()

    finally:

        con.close()


# ============================================================# SOURCE HEALTH
# ============================================================

def source_health(
    source,
    ok,
    count=0,
    error="",
):

    timestamp = now_ist().isoformat()

    con = sqlite3.connect(
        DATABASE
    )

    try:
        columns = {
            row[1]
            for row in con.execute(
                "PRAGMA table_info(source_health)"
            )
        }

        # Ensure both legacy and current fields exist
        if "checked_at" not in columns:

            con.execute(
                """
                ALTER TABLE source_health
                ADD COLUMN checked_at TEXT
                """
            )

        if "checked" not in columns:

            con.execute(
                """
                ALTER TABLE source_health
                ADD COLUMN checked TEXT
                """
            )

        if "ok" not in columns:

            con.execute(
                """
                ALTER TABLE source_health
                ADD COLUMN ok INTEGER
                """
            )

        if "count" not in columns:

            con.execute(
                """
                ALTER TABLE source_health
                ADD COLUMN count INTEGER
                """
            )

        if "error" not in columns:

            con.execute(
                """
                ALTER TABLE source_health
                ADD COLUMN error TEXT
                """
            )

        con.execute(
            """
            INSERT INTO source_health
            (
                source,
                checked_at,
                checked,
                ok,
                count,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source)
            DO UPDATE SET
                checked_at=excluded.checked_at,
                checked=excluded.checked,
                ok=excluded.ok,
                count=excluded.count,
                error=excluded.error
            """,
            (
                source,
                timestamp,
                timestamp,
                int(ok),
                int(count),
                str(error)[:1500],
            ),
        )

        con.commit()

    finally:

        con.close()


# ============================================================
# TOPIC DETECTION
# ============================================================

def topics_for(text):

    normalized = normalize(
        text
    )

    found = []

    for topic, terms in TOPICS.items():

        for term in terms:

            if normalize(term) in normalized:

                found.append(
                    topic
                )

                break

    return found


# ============================================================
# STATIC RESOURCE FILTER
# ============================================================

def static_resource(
    url,
    title,
):

    value = (
        str(url)
        + " "
        + str(title)
    ).lower()

    return any(
        pattern in value
        for pattern in STATIC_PATTERNS
    )


def low_value(text):

    normalized = normalize(
        text
    )

    return any(
        normalize(term) in normalized
        for term in LOW_VALUE
    )


# ============================================================
# LINKS
# ============================================================

def links_from_page(
    base_url,
    html,
):

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    output = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        title = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not title:
            continue

        url = urljoin(
            base_url,
            anchor["href"],
        )

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        output.append(
            (
                title,
                url,
            )
        )
    return output
# ============================================================# ARTICLE METADATA# ============================================================

def inspect_article(url):

    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        is_pdf = "application/pdf" in content_type or urlparse(response.url).path.lower().endswith(".pdf")
        if is_pdf:
            reader = PdfReader(io.BytesIO(response.content))
            extracted = clean_text(" ".join((page.extract_text() or "") for page in reader.pages[:35]))
            return {"title": "", "summary": "", "published": extract_date(extracted), "body": extracted[:20000]}

        soup = BeautifulSoup(response.text, "html.parser")
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
        meta = soup.find("meta", attrs={"name": "description"})
        description = clean_text(meta.get("content", "")) if meta else ""
        published = None
        selectors = [
            "time[datetime]", "meta[property='article:published_time']",
            "meta[property='og:article:published_time']", "meta[name='date']",
            "meta[name='pubdate']", "meta[name='publication_date']",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            value = node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)
            published = parse_date(value) or extract_date(value)
            if published:
                break
        body = clean_text(soup.get_text(" ", strip=True))
        return {"title": title, "summary": description, "published": published, "body": body[:20000]}
    except Exception as exc:
        return {"title": "", "summary": "", "published": None, "body": "", "error": str(exc)[:300]}


# ============================================================
# NEWS SCORING
# ============================================================

def news_score(item):

    text = normalize(
        item["title"]
        + " "
        + item.get(
            "summary",
            "",
        )
        + " "
        + item.get(
            "body",
            "",
        )[:3000]
    )

    score = 0

    # Source authority
    if item.get(
        "official"
    ):

        score += 10

    # Indian relevance
    indian_terms = [
        "india",
        "indian",
        "isha",
        "rci",
        "ncahp",
        "aiish",
        "ayjnih",
        "pgimer",
        "aiims",
        "nimhans",
        "government of india",
    ]

    if any(
        normalize(term) in text
        for term in indian_terms
    ):

        score += 7

    # Topic relevance
    score += min(
        10,
        len(
            item.get(
                "topics",
                [],
            )
        ) * 2,
    )

    # High-value development terms    for term in HIGH_VALUE:

        if normalize(term) in text:

            score += 2

    # Current article signal
    if item.get(
        "published"
    ):

        age = (
            now_ist()
            -
            item["published"]
        ).days

        if age <= 1:

            score += 8

        elif age <= 3:

            score += 5

        elif age <= 7:

            score += 2

    # Static/consumer penalties
    for term in LOW_VALUE:

        if normalize(term) in text:

            score -= 7

    return score


# ============================================================
# NEWS COLLECTION
# ============================================================

def collect_news(
    config
):

    candidates = []

    for source in config.get(
        "news_sources",
        [],
    ):

        name = source.get(
            "name",
            "Unknown",
        )

        url = source.get(
            "url",
            "",
        )

        if not url:
            continue

        accepted = 0

        try:

            html = fetch(
                url
            )

            links = links_from_page(
                url,
                html,
            )

            for link_title, link_url in links[:700]:

                # Cheap first-pass filter
                quick_text = (
                    link_title
                    + " "
                    + link_url
                )

                detected = topics_for(
                    quick_text
                )
                if not detected:

                    continue

                if static_resource(
                    link_url,
                    link_title,
                ):

                    continue

                # We deliberately do NOT reject
                # merely because the title contains
                # words like "research" or "clinical".

                article = inspect_article(
                    link_url
                )

                title = (
                    article["title"]
                    or link_title
                )

                summary = article[
                    "summary"
                ]

                body = article[
                    "body"
                ]

                combined = (
                    title
                    + " "
                    + summary
                    + " "
                    + body
                )

                # Recruitment notices belong in the dedicated vacancy section.
                normalized_headline = normalize(title + " " + summary)
                job_notice = any(
                    normalize(term) in normalized_headline
                    for term in [
                        "recruitment", "vacancy", "vacancies",
                        "applications invited", "walk in interview",
                        "job opening", "last date to apply",
                    ]
                )
                if job_notice and (
                    has_relevant_role(combined)
                    or has_relevant_qualification(combined)
                ):
                    continue

                detected = topics_for(
                    combined
                )

                if not detected:

                    continue

                published = (
                    article["published"]
                    or extract_date(
                        combined
                    )
                )

                if not published:

                    continue

                if published.date() > today():

                    continue

                age = (
                    today()
                    -
                    published.date()
                ).days

                if age < 0 or age > NEWS_DAYS:

                    continue

                if low_value(
                    title
                    + " "
                    + summary
                ):

                    continue

                item = {
                    "title":
                        title,

                    "url":
                        link_url,

                    "source":
                        name,

                    "official":
                        bool(
                            source.get(
                                "official",
                                False,
                            )
                        ),

                    "topics":
                        detected,

                    "published":
                        published,

                    "summary":
                        summary,

                    "body":
                        body,
                }

                item["score"] = news_score(
                    item
                )

                # Strong relevance threshold
                if item["score"] < 14:

                    continue

                item["key"] = hash_key(
                    title
                )

                if was_seen(
                    item["key"]
                ):

                    continue

                candidates.append(
                    item
                )

                accepted += 1

            source_health(
                name,
                True,
                accepted,
            )

        except Exception as exc:

            source_health(
                name,
                False,
                0,
                str(exc),
            )

    # Deduplicate by canonical URL and near-identical titles.
    clusters = []
    for item in candidates:
        if not item.get("title") or not item.get("url"):
            continue
        parsed = urlparse(item["url"])
        canonical = (parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/"))
        normalized_title = normalize(item["title"])
        match = None
        for cluster in clusters:
            rep_item = cluster[0]
            rep_url = urlparse(rep_item["url"])
            rep_canonical = (rep_url.netloc.lower().removeprefix("www."), rep_url.path.rstrip("/"))
            rep_title = normalize(rep_item["title"])
            ratio = difflib.SequenceMatcher(None, normalized_title, rep_title).ratio()
            a, b = set(normalized_title.split()), set(rep_title.split())
            overlap = len(a & b) / max(1, len(a | b))
            if canonical == rep_canonical or ratio >= 0.86 or overlap >= 0.82:
                match = cluster
                break
        if match is None:
            clusters.append([item])
        else:
            match.append(item)

    final = []
    for cluster in clusters:
        cluster.sort(key=lambda x: (x.get("score", 0), bool(x.get("official")), bool(x.get("published"))), reverse=True)
        best = cluster[0]
        best["sources"] = list(dict.fromkeys(item.get("source", "") for item in cluster if item.get("source")))
        final.append(best)
    final.sort(key=lambda x: (x.get("score", 0), x.get("published") or now_ist()), reverse=True)
    return final[:MAX_NEWS]


# ============================================================
# CONFERENCES
# ============================================================

# Known high-priority events are used as seeds.
# The system can also read additional conference
# records supplied in feeds_v7_2_0.yaml.

KNOWN_CONFERENCES = [

    {
        "name":
            "ISHACON 2027",

        "start":
            "2027-01-29",

        "end":
            "2027-01-31",

        "location":
            "Visakhapatnam, Andhra Pradesh, India",

        "organizer":
            "Indian Speech-Language and Hearing Association",

        "url":
            "https://ishacon2027.com/",

        "priority":
            100,
    },

    {
        "name":
            "AAA Annual Convention 2027",

        "start":
            "2027-04-07",

        "end":
            "2027-04-10",

        "location":
            "USA",

        "organizer":
            "American Academy of Audiology",

        "url":
            "https://www.audiology.org/",

        "priority":
            90,
    },
]


def verify_conference(
    event
):

    try:

        html = fetch(
            event["url"]
        )

        text = normalize(
            BeautifulSoup(
                html,
                "html.parser",
            ).get_text(
                " ",
                strip=True,
            )
        )

        event_words = [
            word
            for word in normalize(
                event["name"]
            ).split()
            if len(word) > 3
        ]

        matches = sum(
            word in text
            for word in event_words        )

        return matches >= 1

    except Exception:

        return False


def collect_conferences(
    config
):

    all_events = []
    all_events.extend(
        KNOWN_CONFERENCES
    )    all_events.extend(
        config.get(
            "conferences",
            [],
        )
    )

    unique = {}
    for event in all_events:
        try:

            start = date.fromisoformat(
                event["start"]
            )

        except Exception:

            continue

        days = (
            start
            -
            today()
        ).days

        if days < MIN_CONFERENCE_DAYS:

            continue

        if not verify_conference(
            event
        ):

            continue

        key = hash_key(
            event["name"]
        )

        event = dict(
            event
        )

        event[
            "days_away"
        ] = days

        unique[key] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda x:
            (
                x.get(
                    "priority",
                    50,
                ),
                -x[
                    "days_away"
                ],
            ),
        reverse=True,
    )

    return events[
        :MAX_CONFERENCES
    ]


# ============================================================
# GOVERNMENT JOBS
# ============================================================

def government_domain(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    return host.endswith((".gov.in", ".nic.in", ".edu.in", ".ac.in")) or host == "gov.in"


def extract_deadline(text):
    patterns = [
        r"(?:last date|last day|closing date|deadline|apply before|applications close|last date for application|last date to apply|submission deadline).{0,220}?(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})",
        r"(?:last date|last day|closing date|deadline|apply before|applications close|last date for application|last date to apply|submission deadline).{0,220}?((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})",
        r"(?:last date|deadline|closing date|last date to apply|submission deadline).{0,180}?(20\d{2}-\d{1,2}-\d{1,2})",
        r"(?:last date|deadline|closing date|last date to apply|submission deadline).{0,180}?(\d{1,2}/\d{1,2}/20\d{2})",
        r"(?:last date|deadline|closing date|last date to apply|submission deadline).{0,180}?(\d{1,2}[.-]\d{1,2}[.-]20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed.date()
    return None


def has_relevant_qualification(text):
    normalized = normalize(text)
    return any(normalize(term) in normalized for term in JOB_QUALIFICATION_TERMS)


def has_relevant_role(text):
    normalized = normalize(text)    return any(normalize(term) in normalized for term in JOB_TERMS)


def job_link_candidate(title, url):
    combined = normalize(str(title) + " " + str(url))
    signals = JOB_TERMS + JOB_QUALIFICATION_TERMS + JOB_SIGNALS + [
        "career", "careers", "jobs", "job opening", "employment",
        "advertisement", "recruitment", "notification", "paramedical",
        "project staff", "technical support", "research assistant",
    ]
    return any(normalize(term) in combined for term in signals)


def genuine_vacancy(title, text):
    title_text = normalize(title)
    combined = normalize(title + " " + text)
    if any(normalize(term) in title_text for term in JOB_EXCLUDE):
        return False
    if not (has_relevant_role(combined) or has_relevant_qualification(combined)):
        return False
    return any(normalize(term) in combined for term in JOB_SIGNALS)


def qualification_evidence(text):
    if not text:
        return ""
    sentences = re.split(r"(?<=[.;])s+|
+", text)
    markers = [
        r"B.?s*A.?s*S.?s*L.?s*P.?", r"M.?s*A.?s*S.?s*L.?s*P.?",
        r"BASLP", r"MASLP",
        r"bachelor.{0,70}(?:audiology|speech.{0,15}language|speech.{0,15}hearing)",
        r"master.{0,70}(?:audiology|speech.{0,15}language|speech.{0,15}hearing)",
        r"M.?s*Sc.?.{0,50}(?:audiology|speech.{0,15}language|speech.{0,15}hearing)",
    ]
    for sentence in sentences:
        if any(re.search(pattern, sentence, re.I) for pattern in markers):
            cleaned = clean_text(sentence)
            if cleaned:
                return cleaned[:260]
    return ""


def collect_jobs(config):
    jobs = []
    generic_index_titles = {
        "career", "careers", "recruitment", "recruitment notices",
        "vacancy", "vacancies", "current vacancies", "job openings",
        "job opportunities", "employment opportunities", "notifications",
        "recruitment and careers", "career opportunities",
    }

    for source in config.get("job_sources", []):
        name, url = source.get("name", "Unknown"), source.get("url", "")
        if not url:
            continue
        accepted = 0
        try:
            source_links = links_from_page(url, fetch(url))
            candidate_links = []
            seen_links = set()

            def add_candidate(title, link):
                if not job_link_candidate(title, link):
                    return
                parsed = urlparse(link)
                canonical = (parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/"))
                if canonical in seen_links:
                    return
                seen_links.add(canonical)
                candidate_links.append((title, link))

            # Crawl one level into official career/recruitment index pages.
            for title, link in source_links[:1200]:
                if normalize(title) in generic_index_titles:
                    try:
                        nested = links_from_page(link, fetch(link))
                        for child_title, child_link in nested[:1200]:
                            add_candidate(child_title, child_link)
                    except Exception:
                        continue
                else:
                    add_candidate(title, link)

            for title, link in candidate_links[:220]:
                if not government_domain(link) and not source.get("official", False):
                    continue
                article = inspect_article(link)
                page_title = article.get("title") or clean_text(title)
                body = article.get("body", "")
                combined = page_title + " " + title + " " + body
                if not page_title or not link or not genuine_vacancy(page_title + " " + title, body):
                    continue
                deadline = extract_deadline(body) or extract_deadline(combined)
                if not deadline or deadline < today():
                    continue
                if any(normalize(term) in normalize(page_title + " " + title) for term in JOB_EXCLUDE):
                    continue
                if not (has_relevant_role(combined) or has_relevant_qualification(combined)):
                    continue
                jobs.append({
                    "title": page_title, "institution": name, "url": link,
                    "deadline": deadline, "qualification": qualification_evidence(body),
                    "source": name,
                })
                accepted += 1

            source_health("JOB:" + name, True, accepted)
        except Exception as exc:
            source_health("JOB:" + name, False, 0, str(exc))

    unique = {}
    for job in jobs:
        parsed = urlparse(job["url"])
        host = parsed.netloc.lower().removeprefix("www.")
        key = hash_key(normalize(job["title"]) + " " + host + " " + job["deadline"].isoformat())
        if key not in unique or (not unique[key].get("qualification") and job.get("qualification")):
            unique[key] = job
    jobs = [
        job for job in unique.values()
        if job.get("title") and job.get("institution") and job.get("url") and job.get("deadline")
    ]
    jobs.sort(key=lambda item: (item["deadline"], item["institution"], item["title"]))
    return jobs


# ============================================================
# PROFESSIONAL IMPACT
# ============================================================

def professional_impact(
    item
):

    text = normalize(
        item["title"]
        + " "
        + item.get(
            "summary",
            "",
        )
    )

    if any(
        word in text
        for word in [
            "cpt",
            "reimbursement",
            "medicare",            "payment",
            "coding",
        ]
    ):

        return (
            "Potential implications for "
            "clinical coding, reimbursement "
            "and service delivery."
        )

    if any(
        word in text
        for word in [
            "guideline",
            "consensus",
            "recommendation",
            "standard",
        ]
    ):

        return (
            "May influence evidence-based "
            "assessment, treatment or "
            "professional practice."
        )

    if any(
        word in text
        for word in [
            "artificial intelligence",
            "machine learning",
            "technology",
            "device",
        ]
    ):

        return (
            "Potential implications for "
            "clinical technology, diagnostics "
            "or rehabilitation."
        )

    if any(
        word in text
        for word in [
            "research",
            "study",
            "clinical trial",
        ]
    ):

        return (
            "Relevant new evidence that may "
            "inform clinical practice or future research."
        )

    return (
        "Potential relevance to clinical "
        "practice, research or professional development."
    )


# ============================================================
# FORMAT
# ============================================================

def format_news(news):
    items = [
        item for item in news
        if item.get("title") and item.get("url") and item.get("source")
    ]
    lines = ["CLINICAL, RESEARCH, POLICY & TECHNOLOGY UPDATES", ""]
    if not items:
        lines.append("No qualifying, non-duplicate updates were verified in the current 7-day monitoring window.")
        return "\n".join(lines)
    for index, item in enumerate(items, 1):
        topics = [topic for topic in item.get("topics", []) if topic]
        sources = [source for source in item.get("sources", []) if source]
        if not sources and item.get("source"):
            sources = [item["source"]]
        lines.extend([
            f"{index}. {item['title']}",
            f"Source: {', '.join(dict.fromkeys(sources))}",
        ])
        if topics:
            lines.append("Area: " + ", ".join(topics[:4]))
        impact = professional_impact(item)
        if impact:
            lines.append("Professional relevance: " + impact)
        lines.append("Source link: " + item["url"])
        lines.append("")
    return "\n".join(lines).rstrip()


def format_conferences(conferences):
    items = [
        event for event in conferences
        if event.get("name") and event.get("url") and event.get("start")
        and event.get("end") and event.get("location") and event.get("organizer")
    ]
    lines = ["UPCOMING PROFESSIONAL CONFERENCES", ""]
    if not items:
        lines.append("No verified conference meeting the 90-day advance-notice criterion was found.")
        return "\n".join(lines)
    for index, event in enumerate(items, 1):
        lines.extend([
            f"{index}. {event['name']}",
            f"Dates: {event['start']} to {event['end']} ({event['days_away']} days away)",
            f"Location: {event['location']}",
            f"Organizer: {event['organizer']}",
            f"Official event link: {event['url']}",
            "",
        ])
    return "\n".join(lines).rstrip()


def format_jobs(jobs):
    items = [
        job for job in jobs
        if job.get("title") and job.get("institution") and job.get("url")
        and job.get("deadline") and job["deadline"] >= today()
    ]
    # Do not include a vacancy heading or a "no openings" message when empty.
    if not items:
        return ""

    lines = [
        "INDIAN GOVERNMENT / PUBLIC-SECTOR VACANCIES — OPEN AS OF "
        + today().strftime("%d %B %Y"),
        "",
    ]
    for index, job in enumerate(items, 1):
        remaining = (job["deadline"] - today()).days
        lines.extend([
            f"{index}. {job['title']}",
            f"Institution / recruitment source: {job['institution']}",
        ])
        if job.get("qualification"):
            lines.append("Qualification evidence: " + job["qualification"])
        lines.append(
            f"Application deadline: {job['deadline'].strftime('%d %B %Y')} "
            f"({remaining} day{'s' if remaining != 1 else ''} remaining)"
        )
        lines.append("Official notice/application link: " + job["url"])
        lines.append("")
    return "\n".join(lines).rstrip()


# ============================================================
# SOURCE HEALTH SUMMARY
# ============================================================

def health_summary():

    con = sqlite3.connect(
        DATABASE
    )

    try:

        rows = con.execute(
            """
            SELECT
                ok,
                COUNT(*)
            FROM source_health
            GROUP BY ok
            """
        ).fetchall()

    finally:

        con.close()

    good = 0
    failed = 0

    for ok, count in rows:

        if ok:

            good += count

        else:

            failed += count

    return (
        f"{good} sources verified; "
        f"{failed} source(s) unavailable."
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    message
):

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not token or not chat_id:

        print(
            "Telegram secrets unavailable."
        )

        return

    response = requests.post(
        (
            "https://api.telegram.org/"
            f"bot{token}/sendMessage"
        ),
        json={
            "chat_id":
                chat_id,

            "text":
                message,

            "disable_web_page_preview":
                True,
        },
        timeout=25,
    )

    response.raise_for_status()


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting ISHA Professional "
        "Intelligence V7.2.0..."
    )

    init_database()

    if not CONFIG_FILE.exists():

        raise FileNotFoundError(
            (
                "Missing configuration: "
                f"{CONFIG_FILE}"
            )
        )

    config = yaml.safe_load(
        CONFIG_FILE.read_text(            encoding="utf-8"
        )
    ) or {}
    print(
        "Collecting clinical/research/policy "        "information..."
    )

    news = collect_news(
        config    )

    print(        f"News retained: {len(news)}"
    )

    print(
        "Checking conferences..."
    )

    conferences = collect_conferences(
        config
    )

    print(
        f"Conferences retained: "
        f"{len(conferences)}"
    )

    print(
        "Checking government vacancies..."
    )
    jobs = collect_jobs(
        config
    )

    print(
        f"Jobs retained: {len(jobs)}"
    )

    message = "\n\n".join(
        part for part in [
            "SPEECH, LANGUAGE, HEARING & COMMUNICATION",
            "DAILY PROFESSIONAL INTELLIGENCE",

            (
                f"Date: {today().strftime('%d %B %Y')}\n"
                f"Time: {now_ist().strftime('%I:%M %p')} IST"
            ),

            format_news(
                news
            ),

            format_conferences(
                conferences
            ),

            format_jobs(
                jobs
            ),

            "SOURCE STATUS\n" + health_summary(),

            "Editorial standard: expired vacancies, results, static pages, incomplete entries and duplicate stories are excluded.",
        ] if part.strip()
    )

    # Save complete alert
    alert_file = (
        AUDIT_DIR
        /
        (
            "alert_"
            + today().isoformat()
            + "_v7_2_0.txt"
        )
    )

    alert_file.write_text(
        message,
        encoding="utf-8",
    )

    # Remember reported items
    for item in news:

        remember(
            item["key"],
            "news",
            item["title"],
            item["url"],
        )

    for event in conferences:

        remember(
            hash_key(
                event["name"]
            ),
            "conference",
            event["name"],
            event["url"],
        )

    for job in jobs:

        remember(
            hash_key(
                job["title"]
                + " "
                + job["institution"]
            ),
            "job",
            job["title"],
            job["url"],
        )

    print("")
    print("=" * 70)
    print(message)
    print("=" * 70)

    send_telegram(
        message
    )


if __name__ == "__main__":

    main()
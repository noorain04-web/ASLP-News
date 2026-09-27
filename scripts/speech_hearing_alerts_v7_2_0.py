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
import warnings
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml

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

MAX_NEWS = 6
MAX_CONFERENCES = 3
MAX_JOBS = 5

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
    "audiologist",
    "audiology",
    "speech therapist",
    "speech-language pathologist",
    "speech language pathologist",
    "speech and language therapist",
    "speech-language therapist",
    "audiologist and speech therapist",
    "audiologist & speech therapist",
]

JOB_SIGNALS = [
    "recruitment",
    "recruiting",
    "vacancy",
    "vacancies",
    "apply",
    "application",
    "appointment",
    "walk-in",
    "walk in",
    "last date",
    "closing date",
    "deadline",
    "applications invited",
    "online application",
    "eligible candidates",
    "applications are invited",
]

JOB_EXCLUDE = [
    "result",
    "results",
    "admission",
    "course",
    "training",
    "internship",
    "fellowship",
    "consultant",
    "consultancy",
    "honorary",
    "volunteer",
    "scope of practice",
    "syllabus",
    "curriculum",
    "practice portal",
    "department of audiology",
    "department of speech",
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
            str(value),
            fuzzy=True,
        )

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


# ============================================================
# SOURCE HEALTH
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


# ============================================================
# ARTICLE METADATA
# ============================================================

def inspect_article(
    url
):

    try:

        html = fetch(
            url
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        title = ""

        if soup.title:

            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        description = ""

        meta = soup.find(
            "meta",
            attrs={
                "name":
                    "description"
            },
        )

        if meta:

            description = clean_text(
                meta.get(
                    "content",
                    "",
                )
            )

        published = None

        selectors = [
            "time[datetime]",
            "meta[property='article:published_time']",
            "meta[property='og:article:published_time']",
            "meta[name='date']",
            "meta[name='pubdate']",
            "meta[name='publication_date']",
        ]

        for selector in selectors:

            node = soup.select_one(
                selector
            )

            if not node:
                continue

            value = (
                node.get(
                    "datetime"
                )
                or node.get(
                    "content"
                )
                or node.get_text(
                    " ",
                    strip=True,
                )
            )

            published = (
                parse_date(value)
                or extract_date(value)
            )

            if published:

                break

        body = clean_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        return {
            "title": title,
            "summary": description,
            "published": published,
            "body": body[:10000],
        }

    except Exception:

        return {
            "title": "",
            "summary": "",
            "published": None,
            "body": "",
        }


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

    # High-value development terms
    for term in HIGH_VALUE:

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

    # ========================================================
    # DUPLICATE CLUSTERING
    # ========================================================

    clusters = {}

    for item in candidates:

        normalized_title = normalize(
            item["title"]
        )

        words = [
            w
            for w in normalized_title.split()
            if len(w) > 3
        ]

        cluster_key = hash_key(
            " ".join(
                words[:18]
            )
        )

        clusters.setdefault(
            cluster_key,
            [],
        ).append(
            item
        )

    final = []

    for cluster in clusters.values():

        cluster.sort(
            key=lambda x:
                x["score"],
            reverse=True,
        )

        best = cluster[0]

        best["sources"] = list(
            dict.fromkeys(
                item["source"]
                for item in cluster
            )
        )

        final.append(
            best
        )

    final.sort(
        key=lambda x:
            (
                x["score"],
                x["published"],
            ),
        reverse=True,
    )

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
            for word in event_words
        )

        return matches >= 1

    except Exception:

        return False


def collect_conferences(
    config
):

    all_events = []

    all_events.extend(
        KNOWN_CONFERENCES
    )

    all_events.extend(
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

def government_domain(
    url
):

    host = urlparse(
        url
    ).netloc.lower()

    return (
        ".gov.in" in host
        or
        ".nic.in" in host
        or
        host.endswith(
            ".edu.in"
        )
    )


def extract_deadline(
    text
):

    patterns = [

        r"(?:last date|last day|closing date|deadline|apply before|applications close|last date for application)"
        r".{0,180}?"
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})",

        r"(?:last date|last day|closing date|deadline|apply before|applications close|last date for application)"
        r".{0,180}?"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})",

        r"(?:last date|deadline|closing date)"
        r".{0,150}?"
        r"(20\d{2}-\d{1,2}-\d{1,2})",

        r"(?:last date|deadline|closing date)"
        r".{0,150}?"
        r"(\d{1,2}/\d{1,2}/20\d{2})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text or "",
            re.I,
        )

        if match:

            parsed = parse_date(
                match.group(1)
            )

            if parsed:

                return parsed.date()

    return None


def genuine_vacancy(
    title,
    text,
):

    combined = normalize(
        title
        + " "
        + text
    )

    if not any(
        normalize(term) in combined
        for term in JOB_TERMS
    ):

        return False

    if any(
        normalize(term) in combined
        for term in JOB_EXCLUDE
    ):

        return False

    if not any(
        normalize(term) in combined
        for term in JOB_SIGNALS
    ):

        return False

    return True


def collect_jobs(
    config
):

    jobs = []

    for source in config.get(
        "job_sources",
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

            for title, link in links[:700]:

                if not any(
                    normalize(term)
                    in normalize(
                        title
                        + " "
                        + link
                    )
                    for term in JOB_TERMS
                ):

                    continue

                if not government_domain(
                    link
                ) and not source.get(
                    "official",
                    False,
                ):

                    continue

                article = inspect_article(
                    link
                )

                page_title = (
                    article["title"]
                    or title
                )

                body = article[
                    "body"
                ]

                if not genuine_vacancy(
                    page_title,
                    body,
                ):

                    continue

                deadline = extract_deadline(
                    body
                )

                if not deadline:

                    continue

                if deadline < today():

                    continue

                combined = normalize(
                    page_title
                    + " "
                    + body
                )

                if (
                    "scope of practice"
                    in combined
                    or
                    "curriculum"
                    in combined
                    or
                    "syllabus"
                    in combined
                ):

                    continue

                if (
                    "result"
                    in combined
                    and
                    "apply"
                    not in combined
                ):

                    continue

                jobs.append(
                    {
                        "title":
                            page_title,

                        "institution":
                            name,

                        "url":
                            link,

                        "deadline":
                            deadline,

                        "source":
                            name,
                    }
                )

                accepted += 1

            source_health(
                "JOB:" + name,
                True,
                accepted,
            )

        except Exception as exc:

            source_health(
                "JOB:" + name,
                False,
                0,
                str(exc),
            )

    # Deduplicate
    unique = {}

    for job in jobs:

        key = hash_key(
            job["title"]
            + " "
            + job["institution"]
        )

        unique[key] = job

    jobs = list(
        unique.values()
    )

    jobs.sort(
        key=lambda x:
            x["deadline"]
    )

    return jobs[:MAX_JOBS]


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
            "medicare",
            "payment",
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

def format_news(
    news
):

    lines = [
        "🧠 CLINICAL / RESEARCH / POLICY / TECHNOLOGY",
        "",
    ]

    if not news:

        lines.append(
            "No high-priority, non-duplicate "
            "professional development was verified "
            "in the current 7-day monitoring window."
        )

        return "\n".join(lines)

    for i, item in enumerate(
        news,
        1,
    ):

        topic_text = ", ".join(
            item["topics"][:4]
        )

        sources = ", ".join(
            item.get(
                "sources",
                [
                    item["source"]
                ],
            )
        )

        lines.extend(
            [
                f"{i}. {item['title']}",
                f"🏛️ {sources}",
                f"🧩 Area: {topic_text}",
                (
                    "🎯 Why it matters: "
                    + professional_impact(
                        item
                    )
                ),
                f"🔗 {item['url']}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def format_conferences(
    conferences
):

    lines = [
        "📅 TOP 3 UPCOMING NATIONAL / INTERNATIONAL CONFERENCES",
        "",
    ]

    if not conferences:

        lines.append(
            "No verified professional conference "
            "meeting the ≥90-day criterion was found."
        )

        return "\n".join(lines)

    for i, event in enumerate(
        conferences,
        1,
    ):

        lines.extend(
            [
                f"{i}. {event['name']}",
                (
                    f"📅 {event['start']} to "
                    f"{event['end']} | "
                    f"⏳ {event['days_away']} days away"
                ),
                (
                    f"📍 {event['location']}"
                ),
                (
                    f"🏛️ {event['organizer']}"
                ),
                f"🔗 {event['url']}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def format_jobs(
    jobs
):

    lines = [
        "💼 GOVERNMENT AUDIOLOGY / SLP JOBS — OPEN NOW",
        "",
    ]

    if not jobs:

        lines.append(
            "No verified government Audiology/SLP "
            "vacancy with a future application deadline "
            "was found."
        )

        return "\n".join(lines)

    for i, job in enumerate(
        jobs,
        1,
    ):

        remaining = (
            job["deadline"]
            -
            today()
        ).days

        if remaining <= 3:

            urgency = "🔴"

        elif remaining <= 7:

            urgency = "🟠"

        elif remaining <= 14:

            urgency = "🟡"

        else:

            urgency = "🟢"

        lines.extend(
            [
                (
                    f"{urgency} {i}. "
                    f"{job['title']}"
                ),

                f"🏛️ {job['institution']}",

                (
                    f"📅 Deadline: "
                    f"{job['deadline'].strftime('%d %B %Y')} "
                    f"({remaining} days remaining)"
                ),

                f"🔗 {job['url']}",

                "",
            ]
        )

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
        CONFIG_FILE.read_text(
            encoding="utf-8"
        )
    ) or {}

    print(
        "Collecting clinical/research/policy "
        "information..."
    )

    news = collect_news(
        config
    )

    print(
        f"News retained: {len(news)}"
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
        [
            (
                "📚 SPEECH, LANGUAGE, HEARING "
                "& COMMUNICATION"
            ),

            "DAILY PROFESSIONAL INTELLIGENCE",

            (
                f"📅 {today().strftime('%d %B %Y')}\n"
                f"⏰ {now_ist().strftime('%I:%M %p')} IST"
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

            (
                "🔎 SOURCE STATUS\n"
                + health_summary()
            ),

            (
                "ℹ️ Static practice resources, "
                "generic departmental pages, "
                "expired vacancies, results, "
                "training notices and duplicate "
                "stories are excluded."
            ),
        ]
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

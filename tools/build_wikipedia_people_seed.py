#!/usr/bin/env python3
"""Build a tunable, upload-ready people roster from Wikipedia popularity.

The tool combines rolling monthly Wikipedia pageviews with Wikidata's human
classification. Output is UTF-8, one display name per line, with no header.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path


PAGEVIEWS_ROOT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
HUMAN_QID = "Q5"
DEFAULT_USER_AGENT = "OpenSmash-Wikipedia-roster/1.0 (local character seed builder)"
DEFAULT_QRANK_URL = "https://danker.s3.amazonaws.com/qrank-athaMod-20260801.gz"
DEFAULT_PAGERANK_URL = "https://danker.s3.amazonaws.com/2026-08-06.allwiki.links.rank.bz2"
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUSIONS = PIPELINE_ROOT / "config" / "wikipedia-roster-exclusions.txt"
DEFAULT_INCLUSIONS = PIPELINE_ROOT / "config" / "wikipedia-roster-inclusions.txt"
IGNORED_TITLES = {
    "Main_Page",
    "Special:Search",
    "Wikipedia:Featured_pictures",
}


@dataclass(frozen=True)
class RankedPage:
    title: str
    score: float
    total_views: int
    months_present: int
    median_active_views: float
    peak_views: int


@dataclass(frozen=True)
class Person:
    name: str
    title: str
    qid: str
    qrank: int
    pagerank: float
    qrank_position: int
    pagerank_position: int
    blended_rank_score: float
    pageview_score: float
    total_views: int
    months_present: int
    median_active_views: float
    peak_views: int
    sitelinks: int
    image: str | None


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def unit_float(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def complete_months(count: int, today: date | None = None) -> list[tuple[int, int]]:
    cursor = (today or date.today()).replace(day=1) - timedelta(days=1)
    months = []
    for _ in range(count):
        months.append((cursor.year, cursor.month))
        cursor = cursor.replace(day=1) - timedelta(days=1)
    return months


def page_score(monthly_views: list[int]) -> float:
    active = [views for views in monthly_views if views > 0]
    if not active:
        return float("-inf")
    total = sum(active)
    median_active = statistics.median(active)
    peak = max(active)
    spike_ratio = peak / max(median_active, 1)
    return (
        math.log1p(total)
        + 1.35 * math.log1p(len(active))
        + 0.45 * math.log1p(median_active)
        - 0.40 * math.log1p(spike_ratio)
    )


class WikimediaClient:
    def __init__(self, cache_dir: Path, refresh: bool = False):
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.user_agent = os.environ.get("WIKIMEDIA_USER_AGENT", DEFAULT_USER_AGENT)
        self.last_request_at = 0.0

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        cache_max_age_seconds: float | None = None,
    ) -> dict:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        cache_path = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        cache_is_fresh = (
            cache_max_age_seconds is None
            or time.time() - cache_path.stat().st_mtime <= cache_max_age_seconds
        ) if cache_path.is_file() else False
        if cache_path.is_file() and cache_is_fresh and not self.refresh:
            with cache_path.open(encoding="utf-8") as source:
                return json.load(source)

        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        return self._request_json(request, cache_path, url)

    def post_json(self, url: str, params: dict[str, str]) -> dict:
        body = urllib.parse.urlencode(params).encode()
        cache_key = url.encode() + b"\n" + body
        cache_path = self.cache_dir / f"{hashlib.sha256(cache_key).hexdigest()}.json"
        if cache_path.is_file() and not self.refresh:
            with cache_path.open(encoding="utf-8") as source:
                return json.load(source)
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/sparql-results+json, application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.user_agent,
            },
        )
        return self._request_json(request, cache_path, url)

    def _request_json(
        self, request: urllib.request.Request, cache_path: Path, display_url: str
    ) -> dict:
        error = None
        for attempt in range(6):
            try:
                delay = 0.25 - (time.monotonic() - self.last_request_at)
                if delay > 0:
                    time.sleep(delay)
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                self.last_request_at = time.monotonic()
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                atomic_write(cache_path, json.dumps(payload, ensure_ascii=False))
                return payload
            except urllib.error.HTTPError as caught:
                error = caught
                if caught.code != 429 or attempt == 5:
                    break
                retry_after = caught.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * 2**attempt)
                print(f"Wikimedia rate limit; retrying in {wait:g}s", file=sys.stderr)
                time.sleep(wait)
            except Exception as caught:  # urllib exposes several transient types
                error = caught
                if attempt < 5:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Wikimedia request failed: {display_url}: {error}") from error


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as output:
        output.write(content)
        temporary = Path(output.name)
    os.replace(temporary, path)


def ensure_qrank_file(
    client: WikimediaClient,
    url: str,
    supplied_path: Path | None = None,
) -> Path:
    """Return a cached rolling QRank snapshot, downloading it when needed."""
    if supplied_path:
        if not supplied_path.is_file():
            raise FileNotFoundError(f"QRank file does not exist: {supplied_path}")
        return supplied_path
    filename = Path(urllib.parse.urlparse(url).path).name or "qrank.csv.gz"
    destination = client.cache_dir / filename
    if destination.is_file() and not client.refresh:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": client.user_agent})
    print(f"Downloading QRank snapshot {url}", file=sys.stderr)
    with urllib.request.urlopen(request, timeout=120) as response:
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
            temporary = Path(output.name)
    os.replace(temporary, destination)
    return destination


def load_qranks(path: Path, target_qids: set[str]) -> dict[str, int]:
    """Load only the requested entities from a gzipped QRank CSV."""
    found: dict[str, int] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            qid = row.get("Entity", "")
            if qid in target_qids:
                found[qid] = int(row.get("QRank", 0))
    return found


def load_pageranks(path: Path, target_qids: set[str]) -> dict[str, float]:
    """Load only the requested entities from a bzip2 PageRank TSV."""
    found: dict[str, float] = {}
    with bz2.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            qid, raw_score = line.rstrip().split("\t", 1)
            if qid in target_qids:
                found[qid] = float(raw_score)
    return found


def chunks(values: list[str], size: int = 50):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_ranked_pages(
    client: WikimediaClient,
    language: str,
    months: list[tuple[int, int]],
) -> list[RankedPage]:
    monthly: dict[str, list[int]] = {}
    for month_index, (year, month) in enumerate(months, start=1):
        print(f"[{month_index}/{len(months)}] pageviews {year}-{month:02d}", file=sys.stderr)
        payload = client.get_json(
            f"{PAGEVIEWS_ROOT}/{language}.wikipedia.org/all-access/{year}/{month:02d}/all-days"
        )
        articles = payload.get("items", [{}])[0].get("articles", [])
        for article in articles:
            title = article.get("article", "")
            if (
                not title
                or title in IGNORED_TITLES
                or title.startswith(("Special:", "Wikipedia:", "File:", "Portal:"))
            ):
                continue
            monthly.setdefault(title, [0] * len(months))[month_index - 1] = int(
                article.get("views", 0)
            )

    ranked = []
    for title, views in monthly.items():
        active = [value for value in views if value > 0]
        ranked.append(
            RankedPage(
                title=title,
                score=page_score(views),
                total_views=sum(active),
                months_present=len(active),
                median_active_views=statistics.median(active),
                peak_views=max(active),
            )
        )
    return sorted(ranked, key=lambda page: (-page.score, page.title.casefold()))


def fetch_page_qids(
    client: WikimediaClient, language: str, titles: list[str]
) -> dict[str, str]:
    found: dict[str, str] = {}
    for batch_index, batch in enumerate(chunks(titles), start=1):
        print(f"Wikipedia metadata batch {batch_index}", file=sys.stderr)
        payload = client.get_json(
            f"https://{language}.wikipedia.org/w/api.php",
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": "1",
                "titles": "|".join(batch),
            },
        )
        aliases = {entry["from"]: entry["to"] for entry in payload.get("query", {}).get("normalized", [])}
        aliases.update(
            {entry["from"]: entry["to"] for entry in payload.get("query", {}).get("redirects", [])}
        )
        by_title = {
            page.get("title"): page.get("pageprops", {}).get("wikibase_item")
            for page in payload.get("query", {}).get("pages", [])
        }
        for title in batch:
            resolved = title
            while resolved in aliases and aliases[resolved] != resolved:
                resolved = aliases[resolved]
            qid = by_title.get(resolved)
            if qid:
                found[title] = qid
    return found


def fetch_entities(client: WikimediaClient, qids: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for batch_index, batch in enumerate(chunks(qids), start=1):
        print(f"Wikidata batch {batch_index}", file=sys.stderr)
        payload = client.get_json(
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "claims|labels|sitelinks",
                "languages": "en",
            },
        )
        for qid, entity in payload.get("entities", {}).items():
            entity["sitelinks"] = len(entity.get("sitelinks", {}))
            found[qid] = entity
    return found


def manual_person(name: str) -> tuple[str, dict]:
    """Create deterministic metadata for an explicitly included person without a human page."""
    qid = "manual-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    entity = {
        "claims": {
            "P31": [
                {"mainsnak": {"datavalue": {"value": {"id": HUMAN_QID}}}}
            ]
        },
        "labels": {"en": {"value": name}},
        "sitelinks": 0,
    }
    return qid, entity


def wikipedia_article_url(language: str, title: str) -> str:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="()_',-.")
    return f"https://{language}.wikipedia.org/wiki/{encoded}"


def fetch_human_entities(
    client: WikimediaClient, language: str, titles: list[str]
) -> tuple[dict[str, str], dict[str, dict]]:
    """Resolve ranked articles to humans in large Wikidata graph batches."""
    page_qids: dict[str, str] = {}
    entities: dict[str, dict] = {}
    for batch_index, batch in enumerate(chunks(titles, 200), start=1):
        print(f"Wikidata human batch {batch_index}", file=sys.stderr)
        urls = {wikipedia_article_url(language, title): title for title in batch}
        values = " ".join(f"<{url}>" for url in urls)
        query = f"""
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX schema: <http://schema.org/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?article ?item ?itemLabel ?image ?sitelinks WHERE {{
  VALUES ?article {{ {values} }}
  ?article schema:about ?item;
           schema:isPartOf <https://{language}.wikipedia.org/>.
  ?item wdt:P31 wd:Q5.
  OPTIONAL {{ ?item wdt:P18 ?image. }}
  OPTIONAL {{ ?item wikibase:sitelinks ?sitelinks. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
        payload = client.post_json(WIKIDATA_SPARQL, {"query": query, "format": "json"})
        for row in payload.get("results", {}).get("bindings", []):
            article_url = row.get("article", {}).get("value")
            title = urls.get(article_url)
            item_url = row.get("item", {}).get("value", "")
            qid = item_url.rsplit("/", 1)[-1]
            if not title or not qid.startswith("Q"):
                continue
            page_qids[title] = qid
            label = row.get("itemLabel", {}).get("value")
            if not label or label == qid:
                label = title.replace("_", " ")
            image_url = row.get("image", {}).get("value")
            image = urllib.parse.unquote(image_url.rsplit("/", 1)[-1]) if image_url else None
            raw_sitelinks = row.get("sitelinks", {}).get("value", "0")
            try:
                sitelinks = int(raw_sitelinks)
            except (TypeError, ValueError):
                sitelinks = 0
            entity = entities.setdefault(
                qid,
                {
                    "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": HUMAN_QID}}}}]},
                    "labels": {"en": {"value": label}},
                    "sitelinks": sitelinks,
                },
            )
            entity["sitelinks"] = max(entity.get("sitelinks", 0), sitelinks)
            if image and "P18" not in entity["claims"]:
                entity["claims"]["P18"] = [
                    {"mainsnak": {"datavalue": {"value": image}}}
                ]
    return page_qids, entities


def claim_item_ids(entity: dict, property_id: str) -> list[str]:
    values = []
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            values.append(value["id"])
    return values


def image_name(entity: dict) -> str | None:
    for claim in entity.get("claims", {}).get("P18", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value:
            return value
    return None


def select_people(
    ranked_pages: list[RankedPage],
    page_qids: dict[str, str],
    entities: dict[str, dict],
    qranks: dict[str, int],
    pageranks: dict[str, float],
    pagerank_weight: float,
    limit: int,
    exclusions: set[str],
    inclusions: set[str] | None = None,
    resolved_inclusions: dict[str, str] | None = None,
    require_image: bool = False,
) -> list[Person]:
    inclusions = inclusions or set()
    resolved_inclusions = resolved_inclusions or {}
    candidates = []
    seen_names = set()
    for page in ranked_pages:
        qid = page_qids.get(page.title)
        entity = entities.get(qid or "", {})
        if HUMAN_QID not in claim_item_ids(entity, "P31"):
            continue
        image = image_name(entity)
        if require_image and not image:
            continue
        name = entity.get("labels", {}).get("en", {}).get("value") or page.title.replace("_", " ")
        normalized = " ".join(name.casefold().split())
        if name in exclusions or normalized in seen_names:
            continue
        seen_names.add(normalized)
        candidates.append(
            Person(
                name=name,
                title=page.title,
                qid=qid,
                qrank=qranks.get(qid, 0),
                pagerank=pageranks.get(qid, 0),
                qrank_position=0,
                pagerank_position=0,
                blended_rank_score=0,
                pageview_score=page.score,
                total_views=page.total_views,
                months_present=page.months_present,
                median_active_views=page.median_active_views,
                peak_views=page.peak_views,
                sitelinks=entity.get("sitelinks", 0),
                image=image,
            )
        )
    qrank_positions = {
        person.qid: position
        for position, person in enumerate(
            sorted(candidates, key=lambda person: (-person.qrank, person.name.casefold())),
            start=1,
        )
    }
    pagerank_positions = {
        person.qid: position
        for position, person in enumerate(
            sorted(candidates, key=lambda person: (-person.pagerank, person.name.casefold())),
            start=1,
        )
    }
    scored = []
    for person in candidates:
        qrank_position = qrank_positions[person.qid]
        pagerank_position = pagerank_positions[person.qid]
        blended_rank_score = (
            qrank_position ** (1 - pagerank_weight)
            * pagerank_position**pagerank_weight
        )
        scored.append(
            replace(
                person,
                qrank_position=qrank_position,
                pagerank_position=pagerank_position,
                blended_rank_score=blended_rank_score,
            )
        )
    scored.sort(key=lambda person: (person.blended_rank_score, person.name.casefold()))
    normalized_inclusions = {" ".join(name.casefold().split()) for name in inclusions}
    inclusion_qids = set(resolved_inclusions.values())
    available_inclusions = [
        person
        for person in scored
        if " ".join(person.name.casefold().split()) in normalized_inclusions
        or person.qid in inclusion_qids
    ]
    available_names = {
        " ".join(person.name.casefold().split()) for person in available_inclusions
    }
    missing = sorted(
        name
        for name in inclusions
        if " ".join(name.casefold().split()) not in available_names
        and resolved_inclusions.get(name) not in {person.qid for person in available_inclusions}
    )
    if missing:
        print(
            "Warning: forced inclusions missing from candidate pool: " + ", ".join(missing),
            file=sys.stderr,
        )
    if len(available_inclusions) > limit:
        raise RuntimeError(
            f"{len(available_inclusions)} forced inclusions exceed --limit {limit}"
        )
    forced_qids = {person.qid for person in available_inclusions}
    selected = available_inclusions + [
        person for person in scored if person.qid not in forced_qids
    ][: limit - len(available_inclusions)]
    selected.sort(key=lambda person: (person.blended_rank_score, person.name.casefold()))
    return selected


def read_exclusions(paths: list[Path], inline: list[str]) -> set[str]:
    exclusions = {name.strip() for name in inline if name.strip()}
    for path in paths:
        if path in (DEFAULT_EXCLUSIONS, DEFAULT_INCLUSIONS) and not path.is_file():
            # The default lists are local editorial files (gitignored); a
            # checkout without them simply runs on pure ranking.
            print(f"note: {path.relative_to(PIPELINE_ROOT)} not present, skipping", file=sys.stderr)
            continue
        exclusions.update(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return exclusions


def write_details(path: Path, people: list[Person]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "name",
                "wikipedia_title",
                "wikidata_id",
                "qrank_rolling_12_month_views",
                "pagerank",
                "qrank_position",
                "pagerank_position",
                "blended_rank_score",
                "pageview_score",
                "total_views",
                "months_present",
                "median_active_views",
                "peak_views",
                "sitelinks",
                "image",
            ]
        )
        for person in people:
            writer.writerow(
                [
                    person.name,
                    person.title,
                    person.qid,
                    person.qrank,
                    f"{person.pagerank:.12g}",
                    person.qrank_position,
                    person.pagerank_position,
                    f"{person.blended_rank_score:.6f}",
                    f"{person.pageview_score:.6f}",
                    person.total_views,
                    person.months_present,
                    f"{person.median_active_views:.1f}",
                    person.peak_views,
                    person.sitelinks,
                    person.image or "",
                ]
            )
        temporary = Path(output.name)
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--limit", type=positive_int, default=500, help="exact number of people to output")
    parser.add_argument(
        "--months",
        type=positive_int,
        default=36,
        help="complete monthly top-page lists used for candidate discovery",
    )
    parser.add_argument("--oversample", type=positive_int, default=8, help="raw pages resolved per requested person")
    parser.add_argument(
        "--qrank-url",
        default=DEFAULT_QRANK_URL,
        help="gzipped QRank CSV URL (rolling 12-month Wikimedia views)",
    )
    parser.add_argument("--qrank-file", type=Path, help="local gzipped QRank CSV instead of downloading")
    parser.add_argument(
        "--pagerank-url",
        default=DEFAULT_PAGERANK_URL,
        help="bzip2 all-Wikipedia Wikidata PageRank TSV URL",
    )
    parser.add_argument("--pagerank-file", type=Path, help="local bzip2 PageRank TSV instead of downloading")
    parser.add_argument(
        "--pagerank-weight",
        type=unit_float,
        default=1.0,
        help="PageRank share of the geometric rank blend; 0 is pure QRank",
    )
    parser.add_argument("--language", default="en", help="Wikipedia language subdomain")
    parser.add_argument("--output", type=Path, help="one-name-per-line UTF-8 output path")
    parser.add_argument("--details-output", type=Path, help="optional scored CSV for review")
    parser.add_argument("--exclude", action="append", default=[], help="exact display name to exclude; repeatable")
    parser.add_argument("--exclude-file", action="append", default=[], type=Path, help="newline-delimited exclusions")
    parser.add_argument("--include", action="append", default=[], help="exact display name to force into the final limit; repeatable")
    parser.add_argument("--include-file", action="append", default=[], type=Path, help="newline-delimited forced inclusions")
    parser.add_argument(
        "--no-default-exclusions",
        action="store_true",
        help="do not apply config/wikipedia-roster-exclusions.txt",
    )
    parser.add_argument(
        "--no-default-inclusions",
        action="store_true",
        help="do not apply config/wikipedia-roster-inclusions.txt",
    )
    parser.add_argument("--require-image", action="store_true", help="require a Wikidata P18 image")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/wikipedia-people"))
    parser.add_argument("--refresh", action="store_true", help="ignore cached API responses")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or Path(f"wikipedia-people-{args.limit}.txt")
    client = WikimediaClient(args.cache_dir, refresh=args.refresh)
    ranked = fetch_ranked_pages(client, args.language, complete_months(args.months))
    pool_size = min(len(ranked), max(args.limit * args.oversample, 300))
    ranked_pool = ranked[:pool_size]
    qids, entities = fetch_human_entities(
        client, args.language, [page.title for page in ranked_pool]
    )
    exclusion_files = list(args.exclude_file)
    if not args.no_default_exclusions:
        exclusion_files.insert(0, DEFAULT_EXCLUSIONS)
    exclusions = read_exclusions(exclusion_files, args.exclude)
    inclusion_files = list(args.include_file)
    if not args.no_default_inclusions:
        inclusion_files.insert(0, DEFAULT_INCLUSIONS)
    inclusions = read_exclusions(inclusion_files, args.include)
    resolved_inclusions = fetch_page_qids(client, args.language, sorted(inclusions))
    supplemental_qids = sorted(set(resolved_inclusions.values()) - set(entities))
    entities.update(fetch_entities(client, supplemental_qids))
    for inclusion_name in sorted(inclusions):
        resolved_qid = resolved_inclusions.get(inclusion_name)
        if resolved_qid and HUMAN_QID in claim_item_ids(
            entities.get(resolved_qid, {}), "P31"
        ):
            continue
        manual_qid, manual_entity = manual_person(inclusion_name)
        resolved_inclusions[inclusion_name] = manual_qid
        entities[manual_qid] = manual_entity
    existing_qids = set(qids.values())
    for inclusion_name, qid in resolved_inclusions.items():
        if qid in existing_qids:
            continue
        ranked_pool.append(
            RankedPage(
                title=inclusion_name,
                score=float("-inf"),
                total_views=0,
                months_present=0,
                median_active_views=0,
                peak_views=0,
            )
        )
        qids[inclusion_name] = qid
        existing_qids.add(qid)
    qrank_path = ensure_qrank_file(client, args.qrank_url, args.qrank_file)
    qranks = load_qranks(qrank_path, set(qids.values()))
    pagerank_path = ensure_qrank_file(client, args.pagerank_url, args.pagerank_file)
    pageranks = load_pageranks(pagerank_path, set(qids.values()))
    people = select_people(
        ranked_pool,
        qids,
        entities,
        qranks,
        pageranks,
        args.pagerank_weight,
        args.limit,
        exclusions,
        inclusions,
        resolved_inclusions,
        require_image=args.require_image,
    )
    if len(people) < args.limit:
        raise RuntimeError(
            f"only found {len(people)} eligible people for --limit {args.limit}; "
            "increase --months or --oversample"
        )

    atomic_write(output, "".join(f"{person.name}\n" for person in people))
    if args.details_output:
        write_details(args.details_output, people)
    print(f"Wrote {len(people)} people to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.full_model import RagChunkORM


# =========================================================
# CONFIG
# =========================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Set this to something identifying your application.
#
# Better:
# export NOMINATIM_USER_AGENT="tourism-rag-thesis/1.0 (your@email.com)"
#
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "tourism-rag-thesis/1.0",
)

REQUEST_DELAY_SECONDS = 1.1

COUNTRY_CODE = "vn"

MAX_RESULTS = 5


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_location_value(
    value: Optional[str],
) -> str:
    """
    Normalize text only for grouping DB chunks.

    Dragon Bridge
    dragon bridge
    Dragon Bridge

    -> same group
    """

    if not value:
        return ""

    return " ".join(
        value.strip().lower().split()
    )


def build_geo_key(
    chunk: RagChunkORM,
) -> tuple[str, str, str, str]:
    """
    Unique location identity used for grouping chunks.
    """

    return (
        normalize_location_value(
            chunk.place_name
        ),
        normalize_location_value(
            chunk.city
        ),
        normalize_location_value(
            chunk.province
        ),
        normalize_location_value(
            chunk.country
        ),
    )


# =========================================================
# BUILD GEOCODING QUERY
# =========================================================

def build_geocode_query(
    place_name: str,
    city: Optional[str] = None,
    province: Optional[str] = None,
    country: Optional[str] = None,
) -> str:

    parts = [
        place_name,
        city,
        province,
        country or "Vietnam",
    ]

    # Remove None / empty / duplicate values.
    output = []
    seen = set()

    for part in parts:

        if not part:
            continue

        value = str(part).strip()

        if not value:
            continue

        normalized = value.lower()

        if normalized in seen:
            continue

        seen.add(normalized)
        output.append(value)

    return ", ".join(output)


# =========================================================
# CANDIDATE SCORING
# =========================================================

def score_candidate(
    candidate: dict,
    place_name: str,
    city: Optional[str],
    province: Optional[str],
) -> float:
    """
    Nominatim already ranks results.

    This provides an additional lightweight validation when
    several results are returned in the SAME API call.
    """

    display_name = normalize_location_value(
        candidate.get("display_name")
    )

    address = candidate.get("address") or {}

    address_text = normalize_location_value(
        " ".join(
            str(value)
            for value in address.values()
            if value
        )
    )

    searchable = (
        display_name
        + " "
        + address_text
    )

    score = 0.0

    normalized_place = normalize_location_value(
        place_name
    )

    normalized_city = normalize_location_value(
        city
    )

    normalized_province = normalize_location_value(
        province
    )

    # Place name is most important.
    if normalized_place:

        if normalized_place in searchable:
            score += 10.0

        else:
            # Token overlap for slightly different naming.
            tokens = [
                token
                for token in normalized_place.split()
                if len(token) > 2
            ]

            if tokens:

                matches = sum(
                    token in searchable
                    for token in tokens
                )

                score += (
                    matches / len(tokens)
                ) * 5.0

    # City context.
    if (
        normalized_city
        and normalized_city in searchable
    ):
        score += 4.0

    # Province context.
    if (
        normalized_province
        and normalized_province in searchable
    ):
        score += 2.0

    # Small preference for Nominatim's own importance.
    try:
        score += float(
            candidate.get("importance") or 0
        )
    except (TypeError, ValueError):
        pass

    return score


# =========================================================
# GEOCODER
# =========================================================

def geocode_place_once(
    place_name: str,
    city: Optional[str] = None,
    province: Optional[str] = None,
    country: Optional[str] = None,
) -> Optional[dict]:
    """
    ONE search request for one unique place.

    We request several candidates in that one HTTP call and
    choose the best locally.
    """

    query = build_geocode_query(
        place_name=place_name,
        city=city,
        province=province,
        country=country,
    )

    print(
        f"    Query: {query}"
    )

    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": query,

            "format": "jsonv2",

            # Get multiple candidates in ONE API request.
            "limit": MAX_RESULTS,

            # Restrict result to Vietnam.
            "countrycodes": COUNTRY_CODE,

            # Needed for local candidate validation.
            "addressdetails": 1,

            "accept-language": "en",
        },
        headers={
            "User-Agent": NOMINATIM_USER_AGENT,
        },
        timeout=30,
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        return None

    ranked = sorted(
        results,
        key=lambda candidate: score_candidate(
            candidate=candidate,
            place_name=place_name,
            city=city,
            province=province,
        ),
        reverse=True,
    )

    best = ranked[0]

    return {
        "latitude": float(
            best["lat"]
        ),

        "longitude": float(
            best["lon"]
        ),

        "display_name": best.get(
            "display_name"
        ),

        "osm_type": best.get(
            "osm_type"
        ),

        "osm_id": best.get(
            "osm_id"
        ),

        "place_id": best.get(
            "place_id"
        ),

        "importance": best.get(
            "importance"
        ),

        "match_score": score_candidate(
            candidate=best,
            place_name=place_name,
            city=city,
            province=province,
        ),
    }


# =========================================================
# EXTRA METADATA
# =========================================================

def update_geo_metadata(
    chunk: RagChunkORM,
    *,
    status: str,
    geo: Optional[dict] = None,
):
    """
    Save detailed geocoding information into extra_metadata.

    This lets you inspect/debug bad geo matches later without
    adding many dedicated columns.
    """

    metadata = dict(
        chunk.extra_metadata or {}
    )

    geo_metadata = {
        "status": status,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    if geo:
        geo_metadata.update({
            "display_name": geo.get(
                "display_name"
            ),

            "osm_type": geo.get(
                "osm_type"
            ),

            "osm_id": geo.get(
                "osm_id"
            ),

            "place_id": geo.get(
                "place_id"
            ),

            "importance": geo.get(
                "importance"
            ),

            "match_score": geo.get(
                "match_score"
            ),
        })

    metadata["geo"] = geo_metadata

    # Assign a new dict so SQLAlchemy detects JSONB change.
    chunk.extra_metadata = metadata


# =========================================================
# COPY EXISTING GEO
# =========================================================

def find_existing_geo(
    chunks: list[RagChunkORM],
) -> Optional[RagChunkORM]:
    """
    If one chunk for the same place was already geocoded,
    use it instead of calling API again.
    """

    for chunk in chunks:

        if (
            chunk.latitude is not None
            and chunk.longitude is not None
        ):
            return chunk

    return None


def copy_existing_geo_to_group(
    chunks: list[RagChunkORM],
    source: RagChunkORM,
) -> int:

    updated = 0

    for chunk in chunks:

        if (
            chunk.latitude is not None
            and chunk.longitude is not None
        ):
            continue

        chunk.latitude = source.latitude
        chunk.longitude = source.longitude

        chunk.geocoding_source = (
            source.geocoding_source
            or "db_cache"
        )

        chunk.geocoded_at = (
            source.geocoded_at
            or datetime.now(
                timezone.utc
            )
        )

        update_geo_metadata(
            chunk,
            status="reused_existing_geo",
        )

        updated += 1

    return updated


# =========================================================
# UPDATE GROUP
# =========================================================

def apply_geo_to_group(
    chunks: list[RagChunkORM],
    geo: dict,
) -> int:

    now = datetime.now(
        timezone.utc
    )

    updated = 0

    for chunk in chunks:

        chunk.latitude = (
            geo["latitude"]
        )

        chunk.longitude = (
            geo["longitude"]
        )

        chunk.geocoding_source = (
            "nominatim"
        )

        chunk.geocoded_at = now

        update_geo_metadata(
            chunk,
            status="success",
            geo=geo,
        )

        updated += 1

    return updated


# =========================================================
# MARK NOT FOUND
# =========================================================

def mark_group_not_found(
    chunks: list[RagChunkORM],
):

    for chunk in chunks:

        update_geo_metadata(
            chunk,
            status="not_found",
        )


# =========================================================
# MAIN BACKFILL
# =========================================================

def backfill_chunk_geo():
    """
    Geo-backfill rules:

    1. Only chunks where place_name is populated.
    2. Group all related chunks by:
         place_name + city + province + country.
    3. If one chunk already has geo:
         reuse it, NO API call.
    4. Otherwise:
         ONE geocoding request for the unique place.
    5. Update ALL chunks in that place group.
    6. Commit after each place.
    """

    db: Session = SessionLocal()

    api_requests = 0
    places_success = 0
    places_not_found = 0
    reused_places = 0
    chunks_updated = 0
    places_failed = 0

    try:

        # =================================================
        # LOAD ONLY CHUNKS WITH PLACE NAME
        # =================================================

        chunks = (
            db.query(
                RagChunkORM
            )
            .filter(
                RagChunkORM.place_name.isnot(
                    None
                )
            )
            .filter(
                RagChunkORM.place_name != ""
            )
            .order_by(
                RagChunkORM.city,
                RagChunkORM.place_name,
                RagChunkORM.chunk_index,
            )
            .all()
        )

        print(
            f"Chunks with place_name: "
            f"{len(chunks)}"
        )

        # =================================================
        # GROUP RELATED CHUNKS
        # =================================================

        grouped = defaultdict(list)

        for chunk in chunks:

            grouped[
                build_geo_key(chunk)
            ].append(chunk)

        print(
            f"Unique places: "
            f"{len(grouped)}"
        )

        print()

        # =================================================
        # PROCESS EACH UNIQUE PLACE
        # =================================================

        for index, (
            geo_key,
            group,
        ) in enumerate(
            grouped.items(),
            start=1,
        ):

            example = group[0]

            print(
                f"[{index}/{len(grouped)}] "
                f"{example.place_name}"
                f" | city={example.city}"
                f" | chunks={len(group)}"
            )

            # ---------------------------------------------
            # Are ALL chunks already geocoded?
            # ---------------------------------------------

            missing_geo = [
                chunk
                for chunk in group
                if (
                    chunk.latitude is None
                    or chunk.longitude is None
                )
            ]

            if not missing_geo:

                print(
                    "    [SKIP] All chunks already geocoded."
                )

                continue

            # ---------------------------------------------
            # DB CACHE
            # ---------------------------------------------

            existing = find_existing_geo(
                group
            )

            if existing:

                count = (
                    copy_existing_geo_to_group(
                        chunks=group,
                        source=existing,
                    )
                )

                db.commit()

                chunks_updated += count
                reused_places += 1

                print(
                    f"    [DB CACHE] "
                    f"Updated {count} chunks."
                )

                continue

            # ---------------------------------------------
            # API LOOKUP
            # ---------------------------------------------

            try:

                geo = geocode_place_once(
                    place_name=(
                        example.place_name
                    ),

                    city=(
                        example.city
                    ),

                    province=(
                        example.province
                    ),

                    country=(
                        example.country
                        or "Vietnam"
                    ),
                )

                api_requests += 1

                # Public Nominatim usage policy:
                # stay <= 1 request / second.
                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

                if not geo:

                    print(
                        "    [NOT FOUND]"
                    )

                    mark_group_not_found(
                        group
                    )

                    db.commit()

                    places_not_found += 1

                    continue

                # -----------------------------------------
                # UPDATE EVERY RELATED CHUNK
                # -----------------------------------------

                count = apply_geo_to_group(
                    chunks=group,
                    geo=geo,
                )

                db.commit()

                chunks_updated += count
                places_success += 1

                print(
                    f"    [FOUND] "
                    f"{geo['latitude']}, "
                    f"{geo['longitude']}"
                )

                print(
                    f"    Match: "
                    f"{geo['display_name']}"
                )

                print(
                    f"    Updated {count} chunks."
                )

            except Exception as exc:

                db.rollback()

                places_failed += 1

                print(
                    f"    [FAILED] {exc}"
                )

                # Keep request spacing even after HTTP errors.
                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

        # =================================================
        # SUMMARY
        # =================================================

        print()
        print("=" * 60)
        print("GEO BACKFILL COMPLETE")
        print("=" * 60)

        print(
            f"Unique places: "
            f"{len(grouped)}"
        )

        print(
            f"API requests: "
            f"{api_requests}"
        )

        print(
            f"Places geocoded: "
            f"{places_success}"
        )

        print(
            f"Places reused from DB: "
            f"{reused_places}"
        )

        print(
            f"Places not found: "
            f"{places_not_found}"
        )

        print(
            f"Places failed: "
            f"{places_failed}"
        )

        print(
            f"Chunks updated: "
            f"{chunks_updated}"
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    backfill_chunk_geo()
from config.normalization import (
    TAG_MAPPING,
    TRAVEL_STYLE_MAPPING,
    SUITABLE_FOR_MAPPING,
)


def normalize_list(values, mapping):

    normalized = []

    for value in values:

        value = value.lower().strip()

        if value in mapping:
            value = mapping[value]

        normalized.append(value)

    return sorted(set(normalized))


def normalize_metadata(metadata):

    metadata.ai_tags = normalize_list(
        metadata.ai_tags,
        TAG_MAPPING,
    )

    metadata.ai_travel_styles = normalize_list(
        metadata.ai_travel_styles,
        TRAVEL_STYLE_MAPPING,
    )

    metadata.ai_suitable_for = normalize_list(
        metadata.ai_suitable_for,
        SUITABLE_FOR_MAPPING,
    )

    return metadata 
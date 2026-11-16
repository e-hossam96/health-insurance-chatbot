from __future__ import annotations

from prometheus_client.parser import text_string_to_metric_families


def metric_value(exposition: str, sample_name: str, labels: dict[str, str] | None = None) -> float:
    wanted = labels or {}
    total = 0.0
    for family in text_string_to_metric_families(exposition):
        for sample in family.samples:
            if sample.name == sample_name and all(sample.labels.get(k) == v for k, v in wanted.items()):
                total += sample.value
    return total


def label_sets(exposition: str, prefixes: tuple[str, ...]) -> dict[str, set[tuple[tuple[str, str], ...]]]:
    found: dict[str, set[tuple[tuple[str, str], ...]]] = {}
    for family in text_string_to_metric_families(exposition):
        if not family.name.startswith(prefixes):
            continue
        for sample in family.samples:
            labels = tuple(sorted((k, v) for k, v in sample.labels.items() if k not in ("le", "quantile")))
            found.setdefault(family.name, set()).add(labels)
    return found

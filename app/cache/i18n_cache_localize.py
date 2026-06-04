"""
Apply i18n label swaps to a cached API payload without recomputing data.

Used during cache warmup: build once in the primary language (de), then derive
other languages by replacing catalog strings and resolving title_key fields.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Union

from app.services.i18n_service import Language, i18n_service

JsonValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


def _string_swap_maps(
    catalog: Mapping[str, Mapping[str, str]],
    source: Language,
    target: Language,
) -> Dict[str, str]:
    src = source.value
    tgt = target.value
    out: Dict[str, str] = {}
    for vals in catalog.values():
        if not isinstance(vals, dict):
            continue
        s_val = vals.get(src)
        t_val = vals.get(tgt)
        if not s_val or not t_val or s_val == t_val:
            continue
        out[str(s_val)] = str(t_val)
    return out


def localize_payload_for_language(
    payload: JsonValue,
    source_lang: Language,
    target_lang: Language,
) -> JsonValue:
    """Deep-copy payload with UI strings translated from source_lang to target_lang."""
    if source_lang == target_lang:
        return payload

    catalog = i18n_service._catalog  # noqa: SLF001 — shared catalog is the source of truth
    swap = _string_swap_maps(catalog, source_lang, target_lang)

    def _resolve_title_key(node: MutableMapping[str, Any]) -> None:
        key = node.get("title_key")
        if not key or not isinstance(key, str):
            return
        lang_map = i18n_service._translations.get(target_lang) or {}  # noqa: SLF001
        node["title"] = lang_map.get(key, key)

    def _walk(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for k, v in value.items():
                if k == "title_key":
                    out[k] = v
                    continue
                out[k] = _walk(v)
            if "title_key" in out:
                _resolve_title_key(out)
            return out
        if isinstance(value, list):
            return [_walk(item) for item in value]
        if isinstance(value, str):
            return swap.get(value, value)
        return value

    return _walk(payload)

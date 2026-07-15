"""Model-id validation: fail closed rather than silently substituting a model.

The swarm deliberately pins specific models per role - GPT-class reasoning
for thinking/judging, Composer for executing. A common, quiet failure mode
is a renamed or unavailable model id causing the SDK (or a well-meaning
wrapper) to fall back to *some* model. That would run the whole swarm on the
wrong brain without anyone noticing. So model selection is validated against
the set of ids the calling account can actually see, and any mismatch raises
before a single agent is launched.
"""

from __future__ import annotations

from typing import Iterable, List


class ModelValidationError(RuntimeError):
    """Raised when a required model id is not available to the account."""


def validate_models(required: Iterable[str], available: Iterable[str]) -> None:
    """Ensure every required model id is present in `available`.

    `required` is the set of model ids the configured roles ask for;
    `available` is what `Cursor.models.list()` reports for the calling
    account. Raises `ModelValidationError` listing every missing id so the
    operator fixes the config (or their access) instead of getting a silent
    fallback to the wrong model.
    """
    available_set = set(available)
    missing: List[str] = sorted({m for m in required if m not in available_set})
    if missing:
        raise ModelValidationError(
            "The following configured model id(s) are not available to this "
            f"account: {', '.join(missing)}. Available ids: "
            f"{', '.join(sorted(available_set)) or '(none reported)'}. "
            "Fix orchestrate/swarm.yml or the account's model access - the "
            "swarm will not silently fall back to a different model."
        )


def list_available_model_ids(api_key: str) -> List[str]:
    """Best-effort live lookup of model ids via the Cursor SDK.

    Kept separate from `validate_models` (which is pure) so tests can validate
    the policy without the SDK or a network. Raises if the SDK isn't
    installed; callers that only want the pure check should use
    `validate_models` directly.
    """
    try:
        from cursor_sdk import Cursor
    except ImportError as exc:  # pragma: no cover - exercised only with the extra
        raise ModelValidationError(
            "cursor-sdk is required to list available models. Install it with: "
            "pip install -e '.[orchestrate]'"
        ) from exc

    models = Cursor.models.list(api_key=api_key)
    ids: List[str] = []
    for model in models:
        model_id = getattr(model, "id", None)
        if model_id is None and isinstance(model, dict):
            model_id = model.get("id")
        if model_id:
            ids.append(str(model_id))
    return ids

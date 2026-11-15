"""Context builder (F4, F10): trim chat history for the model."""

from __future__ import annotations

from chatbot_ai.interface import HistoryRow

CONTEXT_LIMIT = 40
TOOL_RESULT_MAX_LEN = 500
TOOL_RESULT_PLACEHOLDER = "[truncated]"


def build_context(rows: list[HistoryRow], limit: int = CONTEXT_LIMIT) -> list[HistoryRow]:
    """Trim history to at most `limit` rows, respecting F4 rules.

    1. Take the last `limit` rows.
    2. Drop leading rows until the first 'user' row, but never split
       a tool-call/result pair. If a split is unavoidable, skip past
       the orphaned rows to the next user row.
    3. Truncate old tool results beyond a size threshold.
    """
    if not rows:
        return []

    tail = rows[-limit:] if len(rows) > limit else list(rows)
    tail = _trim_to_safe_start(tail)
    tail = _truncate_old_tool_results(tail)
    return tail


def _trim_to_safe_start(rows: list[HistoryRow]) -> list[HistoryRow]:
    """Drop leading non-user rows, skipping orphaned tool pairs."""
    # Find all user row indices
    user_indices = [i for i, r in enumerate(rows) if r.role == "user"]
    if not user_indices:
        return rows

    # Try each user index as a cut point (earliest first)
    for idx in user_indices:
        if not _has_orphan_in_range(rows, 0, idx):
            return rows[idx:]

    # All user rows have orphans before them - use the first user row,
    # dropping everything before it (including orphaned tools)
    return rows[user_indices[0]:]


def _has_orphan_in_range(rows: list[HistoryRow], start: int, end: int) -> bool:
    """Check if the range [start, end) contains orphaned tool rows.

    An orphaned tool result has no matching assistant(tool_calls) in the window.
    An orphaned assistant(tool_calls) has results after end.
    """
    for j in range(start, end):
        row = rows[j]
        if (
            row.role == "tool"
            and row.tool_call_id
            and not _has_matching_assistant(rows, start, j, row.tool_call_id)
        ):
            return True
        if (
            row.role == "assistant"
            and row.tool_calls
            and _has_result_after(rows, end, row.tool_calls)
        ):
            return True
    return False


def _has_matching_assistant(
    rows: list[HistoryRow], start: int, tool_idx: int, call_id: str
) -> bool:
    """Check if there's an assistant with a matching tool_call before tool_idx."""
    for k in range(start, tool_idx):
        tcs = rows[k].tool_calls
        if rows[k].role == "assistant" and tcs:
            for tc in tcs:
                if isinstance(tc, dict) and tc.get("id") == call_id:
                    return True
    return False


def _has_result_after(
    rows: list[HistoryRow], after_idx: int, tool_calls: list[dict[str, object]]
) -> bool:
    """Check if any tool result for these tool_calls appears after after_idx."""
    call_ids = {
        tc.get("id")
        for tc in tool_calls
        if isinstance(tc, dict)
    }
    for k in range(after_idx, len(rows)):
        if rows[k].role == "tool" and rows[k].tool_call_id in call_ids:
            return True
    return False


def _truncate_old_tool_results(rows: list[HistoryRow]) -> list[HistoryRow]:
    """Truncate tool results except in the last turn.

    The last turn starts at the last user row. Tool results before that
    are old and should be truncated if they exceed the threshold.
    """
    last_user_idx = -1
    for i in range(len(rows) - 1, -1, -1):
        if rows[i].role == "user":
            last_user_idx = i
            break

    result: list[HistoryRow] = []
    for i, row in enumerate(rows):
        if row.role == "tool" and i < last_user_idx and len(row.content) > TOOL_RESULT_MAX_LEN:
            result.append(HistoryRow(
                role=row.role,
                content=row.content[:TOOL_RESULT_MAX_LEN] + TOOL_RESULT_PLACEHOLDER,
                tool_call_id=row.tool_call_id,
                tool_name=row.tool_name,
            ))
        else:
            result.append(row)
    return result

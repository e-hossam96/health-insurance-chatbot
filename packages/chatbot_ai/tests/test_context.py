from __future__ import annotations

from chatbot_ai.context import (
    STORED_TOOL_RESULT_MAX_LEN,
    TOOL_RESULT_MAX_LEN,
    TOOL_RESULT_PLACEHOLDER,
    build_context,
    cap_stored_tool_result,
    to_openai_messages,
)
from chatbot_ai.interface import HistoryRow


def _user(content: str = "hi") -> HistoryRow:
    return HistoryRow(role="user", content=content)


def _assistant(content: str = "hello") -> HistoryRow:
    return HistoryRow(role="assistant", content=content)


def _tool_call_assistant(call_id: str = "c1") -> HistoryRow:
    return HistoryRow(
        role="assistant",
        content="",
        tool_calls=[{"id": call_id, "type": "function", "function": {"name": "test_fn", "arguments": "{}"}}],
    )


def _tool_result(call_id: str = "c1", content: str = '{"ok": true}') -> HistoryRow:
    return HistoryRow(role="tool", content=content, tool_call_id=call_id, tool_name="test_fn")


def test_F4_limit_to_40_rows() -> None:
    rows = [_user(f"msg {i}") if i % 2 == 0 else _assistant(f"reply {i}") for i in range(60)]
    result = build_context(rows)
    assert len(result) == 40
    assert result[0].content == "msg 20"
    assert result[-1].content == "reply 59"


def test_F4_trim_to_user_start() -> None:
    rows = [_assistant("orphan"), _user("hi"), _assistant("hello")]
    result = build_context(rows)
    assert result[0].role == "user"
    assert len(result) == 2


def test_F4_no_split_tool_call_result() -> None:
    # old messages, then a tool pair, then a user message; the limit forces trimming
    old = [_user(f"old {i}") if i % 2 == 0 else _assistant(f"old {i}") for i in range(38)]
    tool_pair = [_tool_call_assistant("tc1"), _tool_result("tc1")]
    final = [_user("new"), _assistant("done")]
    rows = old + tool_pair + final

    result = build_context(rows, limit=40)
    call_index = next(i for i, r in enumerate(result) if r.role == "assistant" and r.tool_calls)
    assert result[call_index + 1].role == "tool"
    assert result[call_index + 1].tool_call_id == "tc1"
    assert result[0].role == "user"
    assert result[-2:] == final


def test_F4_tool_result_not_orphaned() -> None:
    rows = [
        _tool_call_assistant("c1"),
        _tool_result("c1"),
        _user("question"),
        _assistant("answer"),
    ]
    result = build_context(rows, limit=4)
    # The complete pair before the user can be dropped
    assert result[0].role == "user"
    assert len(result) == 2


def test_F4_truncate_old_tool_results() -> None:
    long_content = "x" * (TOOL_RESULT_MAX_LEN + 100)
    rows = [
        _user("q1"),
        _tool_call_assistant("c1"),
        _tool_result("c1", content=long_content),
        _assistant("a1"),
        _user("q2"),
        _assistant("a2"),
    ]
    result = build_context(rows)
    # The old tool result (before the last user row) should be truncated
    tool_row = next(r for r in result if r.role == "tool")
    assert len(tool_row.content) == TOOL_RESULT_MAX_LEN + len(TOOL_RESULT_PLACEHOLDER)
    assert tool_row.content.endswith(TOOL_RESULT_PLACEHOLDER)


def test_F4_recent_tool_result_not_truncated() -> None:
    long_content = "x" * (TOOL_RESULT_MAX_LEN + 100)
    rows = [
        _user("q1"),
        _tool_call_assistant("c1"),
        _tool_result("c1", content=long_content),
        _assistant("a1"),
    ]
    result = build_context(rows)
    tool_row = next(r for r in result if r.role == "tool")
    assert tool_row.content == long_content


def test_F4_empty_history() -> None:
    assert build_context([]) == []


def test_F4_all_user_rows() -> None:
    rows = [_user(f"msg {i}") for i in range(5)]
    result = build_context(rows)
    assert len(result) == 5
    assert result[0].role == "user"


def test_F4_under_limit_returned_as_is() -> None:
    rows = [_user("hi"), _assistant("hello")]
    result = build_context(rows)
    assert len(result) == 2


def test_F4_trim_skips_past_tool_pair_to_next_user() -> None:
    # a limit of 3 would start at the tool result and orphan it
    rows = [
        _tool_call_assistant("c1"),
        _tool_result("c1"),
        _user("q"),
        _assistant("a"),
    ]
    result = build_context(rows, limit=3)
    # The result should start at the user row and not include orphans
    assert result[0].role == "user"
    assert len(result) == 2


def test_F10_rows_convert_to_openai_messages() -> None:
    rows = [
        _user("book me in"),
        _tool_call_assistant("c1"),
        _tool_result("c1", content='{"slots": []}'),
        _assistant("No slots this week."),
    ]
    assert to_openai_messages(rows) == [
        {"role": "user", "content": "book me in"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "test_fn", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"slots": []}'},
        {"role": "assistant", "content": "No slots this week."},
    ]


def test_F4_stored_tool_result_cap() -> None:
    assert cap_stored_tool_result("short") == "short"
    exact = "z" * STORED_TOOL_RESULT_MAX_LEN
    assert cap_stored_tool_result(exact) == exact
    over = "z" * (STORED_TOOL_RESULT_MAX_LEN + 1)
    assert cap_stored_tool_result(over) == exact + TOOL_RESULT_PLACEHOLDER

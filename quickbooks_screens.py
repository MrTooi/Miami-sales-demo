"""Issue #128, step 6b: the owner's questions about a QuickBooks report, on screen (plan v7, step 6).

One question at a time, with its progress ("Question 2 of 5"), the original row and dollar amount, plain
words first and the codes in small print. Nothing is pre-selected. The owner can skip a question, say "Not
sure yet", go back, change any earlier answer, and see what's left. The report's own problems come first and
the money MargenX holds without asking is always shown with its amount.

What is asked and what an answer can change are decided by quickbooks_questions (step 6a); this screen only
shows them and passes the owner's choice on. Answers live in this browser session only, never on disk.

Not switched on yet: QuickBooks uploads are still refused (job_intake), so no page calls this. The results
screens (step 7) and the switch-on PR come after it.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import streamlit as st

import marginx_ui as ui
import quickbooks_figures as qf
import quickbooks_pnl as qp
import quickbooks_questions as qq

DONE_NOTE = ("No questions left doesn't mean every figure is final. Money MargenX holds (listed below) and any "
             "problem in the report itself keep the figures they touch on \"Needs a check\", whatever the answers. "
             "Each figure shows its own status.")


@dataclasses.dataclass
class _State:
    """This report's answers in this session, and where the owner is."""
    answers: qf.OwnerAnswers
    skipped: list[str] = dataclasses.field(default_factory=list)  # question keys, in the order skipped
    history: list[tuple[qq.Question, str]] = dataclasses.field(default_factory=list)  # (question, choice) saved
    changing: int | None = None  # the history entry being changed, if any
    turn: int = 0  # changes every time a question is saved, so a fresh question never starts with a choice made
    message: str = ""  # what happened to the last answer, shown once


def _state(report: qp.ProfitAndLossDetail, key: str) -> _State:
    fingerprint = qf.report_fingerprint(report)
    name = f"{key}-{fingerprint}"  # another report, or another version of this one, starts afresh
    if name not in st.session_state:
        st.session_state[name] = _State(qf.OwnerAnswers(report=fingerprint))
    return st.session_state[name]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _label(question: qq.Question, value: str) -> str:
    return next((c.label for c in question.choices if c.value == value), value)


def question_screen(report: qp.ProfitAndLossDetail, cross_check=None, *, key: str = "qbo") -> qf.OwnerAnswers:
    """Show the open questions about this report and return the owner's answers so far (bound to the report)."""
    state = _state(report, key)
    listing = qq.open_questions(report, state.answers, cross_check)

    for problem in listing.report_problems:
        st.error(ui.md_text(f"A problem in the report itself: {problem}"))
    for warning in listing.warnings:
        st.warning(ui.md_text(warning))
    if state.message:
        st.info(ui.md_text(state.message))
        state.message = ""

    if state.changing is not None:
        question, previous = state.history[state.changing]
        _ask(report, state, question, cross_check, previous=previous)
    else:
        waiting = [q for q in listing.questions if q.key not in state.skipped]
        if waiting:
            # Progress counts what's answered too: answering can open new questions (jobs, entries), so the
            # total can grow, but the count never goes back to 1.
            done = len(state.history)
            _ask(report, state, waiting[0], cross_check,
                 progress=(done + listing.questions.index(waiting[0]) + 1, done + len(listing.questions)))
        elif listing.questions:
            st.info(f"You skipped {_plural(len(listing.questions), 'question')}. They stay on \"Needs a check\" "
                    "until you answer them.")
            if st.button("Go through the skipped questions", key=f"{key}-again-{state.turn}"):
                state.skipped.clear()
                state.turn += 1
                st.rerun()
        else:
            st.success("No questions left.")
            st.caption(DONE_NOTE)

    _review(state, listing, key)
    return state.answers


def _ask(report: qp.ProfitAndLossDetail, state: _State, question: qq.Question, cross_check, *,
         previous: str | None = None, progress: tuple[int, int] | None = None) -> None:
    widget = f"{question.key}-{state.turn}"
    if previous is None:
        number, total = progress or (question.number, question.total)
        st.markdown(f"**Question {number} of {total}**")
    else:
        st.markdown(f"**Changing an earlier answer.** You said: {ui.md_text(_label(question, previous))}")
    st.subheader(ui.md_text(question.title))
    if question.row is not None:
        st.markdown(ui.md_text(f"Row {question.row} of the report"))
    for line in question.details:
        st.markdown(ui.md_text(line))
    if question.small_print:
        st.caption(ui.md_text(question.small_print))

    values = [c.value for c in question.choices]
    choice = st.radio("Your answer", values, index=None, format_func=lambda v: ui.md_text(_label(question, v)),
                      key=f"choice-{widget}")
    outside = None
    if choice == "outside job":
        outside = st.text_input("The job's name, as you call it", key=f"outside-{widget}")

    save, skip, back = st.columns(3)
    if save.button("Save answer", type="primary", disabled=choice is None, key=f"save-{widget}"):
        _save(report, state, question, choice, outside, cross_check)
        st.rerun()
    if previous is None:
        if skip.button("Skip for now", key=f"skip-{widget}"):
            state.skipped.append(question.key)
            state.turn += 1
            st.rerun()
        if state.history and back.button("Back", key=f"back-{widget}"):
            state.changing = len(state.history) - 1
            state.turn += 1
            st.rerun()
    elif skip.button("Keep my answer", key=f"keep-{widget}"):
        state.changing = None
        state.turn += 1
        st.rerun()


def _save(report: qp.ProfitAndLossDetail, state: _State, question: qq.Question, choice: str, outside: str | None,
          cross_check) -> None:
    new = qq.answer(report, state.answers, question, choice, outside_job=outside, cross_check=cross_check,
                    answered_at=_now())
    state.turn += 1
    if choice == qq.NOT_SURE:
        # "Not sure yet" clears any earlier answer to it (6a) and moves on, like skipping.
        state.answers = new
        if question.key not in state.skipped:
            state.skipped.append(question.key)
        state.history = [(q, c) for q, c in state.history if q.key != question.key]
        state.changing = None
        state.message = "Left on \"Needs a check\". You can come back to it any time."
        return
    if new == state.answers:
        if choice == "outside job" and not (outside or "").strip():
            state.message = "Please type the job's name, or pick another answer."
        else:
            # The question no longer fits (an earlier answer changed what this line is): nothing was saved.
            state.message = ("That question has changed since, so nothing was saved. The questions shown now are "
                             "the current ones.")
            state.changing = None
        return
    state.answers = new
    state.skipped = [k for k in state.skipped if k != question.key]
    state.history = [(q, c) for q, c in state.history if q.key != question.key] + [(question, choice)]
    state.changing = None
    state.message = "Saved."


def _review(state: _State, listing: qq.QuestionList, key: str) -> None:
    answered = len(state.history)
    left = len(listing.questions)
    with st.expander(f"Your answers ({answered}) and what's left ({left})"):
        if not state.history:
            st.caption("No answers yet.")
        for index, (question, choice) in enumerate(state.history):
            text, change = st.columns([4, 1])
            text.markdown(ui.md_text(f"{question.title} → {_label(question, choice)}"))
            if change.button("Change", key=f"{key}-change-{index}-{state.turn}"):
                state.changing = index
                state.turn += 1
                st.rerun()
        if listing.questions:
            st.markdown("**Still to answer**")
            for question in listing.questions:
                skipped = " (skipped)" if question.key in state.skipped else ""
                st.markdown(ui.md_text(f"{question.title}{skipped}"))
    if listing.held_lines:
        total = len(listing.held_lines)
        with st.expander(f"Money MargenX holds without asking ({total})"):
            st.caption("MargenX never counts these lines, so the figures they could change stay on \"Needs a "
                       "check\". Each is shown with its amount.")
            for held in listing.held_lines:
                st.markdown(ui.md_text(held.reason))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")

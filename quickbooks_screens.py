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


def _md(value) -> str:
    """Text for any Streamlit call that reads Markdown: ui.md_text, and every "$" escaped. Streamlit reads the text
    between two "$" as a math formula, so "$5,500.00 so far ... $3,600.00" would show garbled (found in the browser
    in step 7)."""
    return ui.md_text(value).replace("$", "\\$")


@dataclasses.dataclass(frozen=True)
class _Entry:
    """One saved answer, as the owner gave it."""
    question: qq.Question
    choice: str
    shown: str  # in the owner's words, with the job's name for an outside job (the automated review of a2a7063)


@dataclasses.dataclass
class _State:
    """This report's answers in this session, and where the owner is."""
    answers: qf.OwnerAnswers
    name: str  # this screen and this report: every widget key starts with it (the automated review of ebeb09a)
    skipped: list[str] = dataclasses.field(default_factory=list)  # question keys, in the order skipped
    history: list[_Entry] = dataclasses.field(default_factory=list)  # saved answers, oldest first
    changing: int | None = None  # the history entry being changed, if any
    turn: int = 0  # changes every time a question is saved, so a fresh question never starts with a choice made
    message: str = ""  # what happened to the last answer, shown once


def _state(report: qp.ProfitAndLossDetail, key: str) -> _State:
    fingerprint = qf.report_fingerprint(report)
    name = f"{key}-{fingerprint}"  # another report, or another version of this one, starts afresh
    if name not in st.session_state:
        st.session_state[name] = _State(qf.OwnerAnswers(report=fingerprint), name)
    return st.session_state[name]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(question: qq.Question) -> str:
    """What the screen tracks a question by. The no-filter question is about one exact pair of reports, so its
    widgets, skips and saved answer belong to that pair: replacing only the second report asks afresh (the PR #143
    manual review, blocker)."""
    return f"{question.key}@{question.pair}" if question.kind == qq.NO_FILTER else question.key


def _label(question: qq.Question, value: str) -> str:
    return next((c.label for c in question.choices if c.value == value), value)


def _stored(entry: _Entry, answers: qf.OwnerAnswers) -> bool:
    """Whether the answer is still recorded at all (a later answer to another question can replace it)."""
    question = entry.question
    if question.kind == qq.JOBS:
        return answers.sub_customers_are_jobs is (entry.choice == "yes")
    if question.kind == qq.NO_FILTER:
        return answers.unfiltered_pair == question.pair
    if question.kind == qq.ACCOUNT:
        stored = answers.accounts.get(question.account)
        return stored is not None and stored.use == entry.choice
    return _own_line_answer(entry, answers) is not None


def _own_line_answer(entry: _Entry, answers: qf.OwnerAnswers) -> qf.LineAnswer | None:
    """This entry's own line answer: the recorded one, or the owner's classification a job answer builds on."""
    stored = answers.lines.get(entry.question.row)
    if stored is None:
        return None
    if stored.asked == entry.question.key:
        return stored
    if stored.base is not None and stored.base.asked == entry.question.key:
        return stored.base
    return None


def _in_use(entry: _Entry, answers: qf.OwnerAnswers, result: qf.Figures, open_keys: set[str], cross_check) -> bool:
    """Whether a saved answer still counts. A later answer can make an earlier one not apply (sub-customers no
    longer jobs, a line answered as something else): it's then kept but shown apart, never counted as done (the
    automated review of a2a7063)."""
    question = entry.question
    if question.kind == qq.JOBS:
        return answers.sub_customers_are_jobs is (entry.choice == "yes")
    if question.kind == qq.NO_FILTER:
        # Counts only while that very pair is the one in use (the PR #143 manual review, warning).
        return (answers.unfiltered_pair == question.pair and _id(question) not in open_keys
                and cross_check is not None and getattr(cross_check, "usable", False)
                and cross_check.pair == question.pair)
    if question.kind == qq.ACCOUNT:
        stored = answers.accounts.get(question.account)
        return stored is not None and stored.use == entry.choice and _id(question) not in open_keys
    if _own_line_answer(entry, answers) is None:
        return False
    used = next((r.answer for r in result.resolutions if r.row == question.row), None)
    if used != answers.lines.get(question.row):
        return False
    return not question.key.startswith("job:") or entry.choice == qf.OVERHEAD or result.jobs_on


def question_screen(report: qp.ProfitAndLossDetail, cross_check=None, *, key: str = "qbo") -> qf.OwnerAnswers:
    """Show the open questions about this report and return the owner's answers so far (bound to the report)."""
    state = _state(report, key)
    listing = qq.open_questions(report, state.answers, cross_check)
    result = qf.figures(report, state.answers, cross_check=cross_check)
    open_keys = {_id(q) for q in listing.questions}
    in_use = [i for i, e in enumerate(state.history) if _in_use(e, state.answers, result, open_keys, cross_check)]

    for problem in listing.report_problems:
        st.error(_md(f"A problem in the report itself: {problem}"))
    for warning in listing.warnings:
        st.warning(_md(warning))
    if state.message:
        st.info(_md(state.message))
        state.message = ""

    if state.changing is not None:
        entry = state.history[state.changing]
        _ask(report, state, entry.question, cross_check, previous=entry.shown, in_use=in_use)
    else:
        waiting = [q for q in listing.questions if _id(q) not in state.skipped]
        if waiting:
            # Progress counts what's answered too: answering can open new questions (jobs, entries), so the
            # total can grow, but the count never goes back to 1.
            done = len(in_use)
            _ask(report, state, waiting[0], cross_check, in_use=in_use,
                 progress=(done + listing.questions.index(waiting[0]) + 1, done + len(listing.questions)))
        elif listing.questions:
            st.info(f"You skipped {_plural(len(listing.questions), 'question')}. They stay on \"Needs a check\" "
                    "until you answer them.")
            if st.button("Go through the skipped questions", key=f"{state.name}-again-{state.turn}"):
                state.skipped.clear()
                state.turn += 1
                st.rerun()
        else:
            st.success("No questions left.")
            st.caption(DONE_NOTE)

    _review(state, listing, in_use)
    return state.answers


def _ask(report: qp.ProfitAndLossDetail, state: _State, question: qq.Question, cross_check, *,
         previous: str | None = None, progress: tuple[int, int] | None = None, in_use: list[int] = ()) -> None:
    # Every widget belongs to this screen, this report and this turn: another report, or another screen on the
    # page, never inherits a choice or a typed name (the automated review of ebeb09a).
    widget = f"{state.name}-{_id(question)}-{state.turn}"
    if previous is None:
        number, total = progress or (question.number, question.total)
        st.markdown(f"**Question {number} of {total}**")
    else:
        st.markdown(f"**Changing an earlier answer.** You said: {_md(previous)}")
    st.subheader(_md(question.title))
    if question.row is not None:
        st.markdown(_md(f"Row {question.row} of the report"))
    for line in question.details:
        st.markdown(_md(line))
    if question.small_print:
        st.caption(_md(question.small_print))

    values = [c.value for c in question.choices]
    choice = st.radio("Your answer", values, index=None, format_func=lambda v: _md(_label(question, v)),
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
            state.skipped.append(_id(question))
            state.turn += 1
            st.rerun()
        if in_use and back.button("Back", key=f"back-{widget}"):
            state.changing = in_use[-1]
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
    if choice == "outside job" and not (outside or "").strip():
        # Kept on screen as it is (same turn), so the owner only has to type the name.
        state.message = "Please type the job's name, or pick another answer."
        return
    state.turn += 1
    if choice == qq.NOT_SURE:
        # "Not sure yet" clears any earlier answer to it (6a) and moves on, like skipping.
        state.answers = new
        if _id(question) not in state.skipped:
            state.skipped.append(_id(question))
        state.history = [e for e in state.history if _id(e.question) != _id(question) and _stored(e, new)]
        state.changing = None
        state.message = "Left on \"Needs a check\". You can come back to it any time."
        return
    shown = _label(question, choice)
    if choice == "outside job":
        shown = f"A job that isn't in this report: \"{outside.strip()}\""
    if new == state.answers and any(_id(e.question) == _id(question) and e.shown == shown and _stored(e, new)
                                    for e in state.history):
        # The same answer saved again (within the same second, so nothing changed): kept, not "changed since"
        # (the automated review of 1a4bc4a).
        state.changing = None
        state.message = "Your answer is unchanged."
        return
    if new == state.answers:
        # The question no longer fits (an earlier answer changed what this line is): nothing was saved.
        state.message = ("That question has changed since, so nothing was saved. The questions shown now are the "
                         "current ones.")
        state.changing = None
        return
    state.answers = new
    state.skipped = [k for k in state.skipped if k != _id(question)]
    state.history = [e for e in state.history if _id(e.question) != _id(question)] + [_Entry(question, choice, shown)]
    state.history = [e for e in state.history if _stored(e, new)]  # answers replaced by this one are gone
    state.changing = None
    state.message = "Saved."


def _review(state: _State, listing: qq.QuestionList, in_use: list[int]) -> None:
    left = len(listing.questions)
    apart = [i for i in range(len(state.history)) if i not in in_use]
    with st.expander(f"Your answers ({len(in_use)}) and what's left ({left})"):
        if not in_use:
            st.caption("No answers yet.")
        for index in in_use:
            entry = state.history[index]
            text, change = st.columns([4, 1])
            text.markdown(_md(f"{entry.question.title} → {entry.shown}"))
            if change.button("Change", key=f"{state.name}-change-{index}-{state.turn}"):
                state.changing = index
                state.turn += 1
                st.rerun()
        if apart:
            st.markdown("**Earlier answers that don't apply now** (because of a later answer; they count again only if "
                        "you change that answer back)")
            for index in apart:
                entry = state.history[index]
                st.markdown(_md(f"{entry.question.title} → {entry.shown}"))
        if listing.questions:
            st.markdown("**Still to answer**")
            for question in listing.questions:
                skipped = " (skipped)" if _id(question) in state.skipped else ""
                st.markdown(_md(f"{question.title}{skipped}"))
    if listing.held_lines:
        total = len(listing.held_lines)
        with st.expander(f"Money MargenX holds without asking ({total})"):
            st.caption("MargenX never counts these lines, so the figures they could change stay on \"Needs a "
                       "check\". Each is shown with its amount.")
            for held in listing.held_lines:
                st.markdown(_md(held.reason))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")

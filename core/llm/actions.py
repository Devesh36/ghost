"""Typed workflow proposals. Models cannot supply executable commands or flags."""
from enum import StrEnum
import re
import time

from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    SCAN = 'scan'
    BRIEF = 'brief'
    FINDINGS = 'findings'
    SCOPE = 'scope'
    STATUS = 'status'
    DIFF = 'diff'
    SOLUTION = 'solution'
    DOCTOR = 'doctor'
    REVIEW = 'review'
    FIX = 'fix'


class ActionReply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reply: str = Field(min_length=1, max_length=8192)
    action: Action | None


class PendingAction(BaseModel):
    action: Action
    request: str
    repository: str
    created_at: float = Field(default_factory=time.monotonic)


ACCEPT = {'do that', 'do that for me', 'go ahead', 'yes', 'yes please', 'run it', 'run that'}
DECLINE = {'no', 'no thanks', 'cancel', 'never mind', 'nevermind'}


def normalized(question: str) -> str:
    return ' '.join(question.casefold().strip().rstrip('?.!').split())


def direct_action(question: str) -> Action | None:
    """Only explicit common requests; ambiguous proposals require a follow-up."""
    text = normalized(question)
    if re.search(r"\b(?:don't|do not|never|without)\b", text):
        return None
    text = re.sub(r'^(?:please |can you |could you |would you )', '', text)
    if re.match(r'^(?:fix|repair|change|update|modify)\s', text):
        return Action.FIX
    if re.match(r'^(?:scan|check) (?:this |my |the )?(?:repo\b|repository\b|project\b|code\b)', text) or text in {
            'find issues', 'find security issues', 'find risks', 'scan here'}:
        return Action.SCAN
    if re.match(r'^review (?:this |my |the )?(?:repo\b|repository\b|project\b|code\b)', text):
        return Action.REVIEW
    if (re.match(r'^(?:show|list|what are|what were) (?:me )?(?:my |the |your |our |saved |latest )*(?:findings?\b|issues\b|risks\b)', text)
            or re.match(r'^what .*\bfindings?\b', text)):
        return Action.FINDINGS
    if re.match(r'^(?:summarize|brief) (?:my |the |this |latest |saved )*(?:review|findings|issues|risks)', text):
        return Action.BRIEF
    for phrases, action in [({'show scope', 'what files are selected'}, Action.SCOPE),
                            ({'show status', 'show my status'}, Action.STATUS),
                            ({'show diff', 'show my changes', 'show the diff'}, Action.DIFF),
                            ({'show solution', 'show the patch', 'show my solution'}, Action.SOLUTION),
                            ({'check ghost', 'check prerequisites', 'run doctor'}, Action.DOCTOR)]:
        if text in phrases:
            return action
    return None


def arguments(action: Action, request: str) -> list[str]:
    """Host-owned argv only; the request is a literal fix argument after --."""
    action = Action(action)
    if action == Action.SCAN:
        return ['find']
    if action == Action.REVIEW:
        return ['review']
    if action == Action.FIX:
        return ['fix', '--', request]
    return [action.value]

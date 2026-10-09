"""Presentation-only triage of saved candidates; never changes scanner evidence."""
from dataclasses import dataclass
from enum import Enum

from core.security.models import SecurityFinding


class FindingGroup(str, Enum):
    file = 'file'
    rule = 'rule'


LEVELS = ('HIGH', 'MEDIUM', 'LOW', 'UNDEFINED')


def ordered_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    rank = {level: index for index, level in enumerate(LEVELS)}
    return sorted(findings, key=lambda item: (rank[item.severity], rank[item.confidence],
                                               item.path, item.line, item.id))


def filtered_findings(findings, *, severity=None, confidence=None, path=None, rule=None):
    return [item for item in ordered_findings(findings)
            if (severity is None or item.severity == severity)
            and (confidence is None or item.confidence == confidence)
            and (path is None or item.path == path)
            and (rule is None or item.rule == rule)]


def finding_groups(findings, group_by: FindingGroup):
    groups = {}
    for item in findings:
        key = item.path if group_by == FindingGroup.file else item.rule
        groups.setdefault(key, []).append(item)
    return list(groups.items())


@dataclass(frozen=True)
class FindingGuidance:
    meaning: str
    verify: str
    repair: str


GUIDANCE = {
    'B307': FindingGuidance(
        'Expression evaluation can execute code rather than only parse data.',
        'Trace the value into eval. Check who controls it and whether expression evaluation is intended.',
        'For a standalone literal parser, solve can test the supported Python recipe. Other shapes need a manual fix.'),
    'GJS001': FindingGuidance(
        'JavaScript expression evaluation can execute code.',
        'Trace the value into eval and check whether untrusted input can reach it.',
        'Use a data parser or explicit operations that match the intended API. Automatic JS/TS repairs are not supported.'),
    'GJS002': FindingGuidance(
        'Dynamic Function construction creates executable code from text.',
        'Check the origin of arguments and whether runtime code generation is needed.',
        'Prefer explicit functions and validated data. Review and test the change manually.'),
    'GJS003': FindingGuidance(
        'A shell command can interpret input as executable shell syntax.',
        'Trace interpolated command values and distinguish trusted constants from caller-controlled input.',
        'Prefer a process API with separate arguments and no shell, when compatible with the intended behavior.'),
    'GJS004': FindingGuidance(
        'Disabling certificate verification can allow an untrusted server to impersonate the destination.',
        'Check the connection settings and whether this code can run outside a disposable test.',
        'Restore certificate verification and configure the intended trust roots; test against the real destination.'),
    'B501': FindingGuidance(
        'Certificate verification appears to be disabled on an HTTPS request.',
        'Check the request and its runtime configuration; establish whether this path is reachable.',
        'Restore TLS verification and configure supported trust roots rather than bypassing validation.'),
    'B301': FindingGuidance(
        'Pickle deserialization can execute code from the serialized payload.',
        'Establish who can create or replace the payload, including storage and transport boundaries.',
        'Use a data-only format for untrusted payloads, then validate its structure and test compatibility.'),
    'B602': FindingGuidance(
        'A subprocess command runs through a shell.',
        'Check each command component and whether caller-controlled input can change the shell syntax.',
        'Prefer an argument list with shell disabled when compatible; test quoting and supported inputs.'),
}


def guidance_for(rule: str) -> FindingGuidance:
    return GUIDANCE.get(rule, FindingGuidance(
        'The scanner matched a potentially risky source pattern.',
        'Review the reported location, callers, input trust boundaries, and existing safeguards.',
        'Plan a manual change if the risk is applicable, then run project tests and a fresh review.'))

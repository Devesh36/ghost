"""Versioned, independently authored fixtures; no user-supplied dataset execution."""
import ast
import hashlib
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')


class DetectionCase(Case):
    path: str = Field(pattern=r'^[a-z][a-z0-9_]*\.(py|js|ts)$', max_length=100)
    rule: str = Field(pattern=r'^(B|GJS)[0-9]{3}$')
    expected: StrictBool
    source: str = Field(min_length=1, max_length=32_000)
    rationale: str = Field(min_length=1, max_length=1000)


class RepairCase(Case):
    expected: Literal['verified', 'blocked']
    files: dict[str, str]
    refusal: str | None = None

    @model_validator(mode='after')
    def bounded_project(self):
        if set(self.files) != {'parser.py', 'test_baseline.py'}:
            raise ValueError('Repair fixtures need exactly the parser and selected baseline test')
        for source in self.files.values():
            if not 1 <= len(source) <= 32_000:
                raise ValueError('Fixture source exceeds the budget')
            ast.parse(source)
        if self.expected == 'blocked' and not self.refusal:
            raise ValueError('A refusal case must identify its expected scope restriction')
        return self


class EvidenceCase(Case):
    proposal: Literal['literal_recipe', 'reject_all', 'still_executes']
    contract: str = Field(min_length=1, max_length=32_000)
    expected: Literal['supported', 'not_supported', 'inconclusive']


class Corpus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1]
    id: Literal['ghost-security-eval-v1']
    synthetic: Literal[True]
    detection: list[DetectionCase] = Field(min_length=1, max_length=100)
    repairs: list[RepairCase] = Field(min_length=1, max_length=20)
    evidence: list[EvidenceCase] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def distinct_cases(self):
        cases = [*self.detection, *self.repairs, *self.evidence]
        if len({case.id for case in cases}) != len(cases):
            raise ValueError('Case IDs must be distinct')
        if len({case.path for case in self.detection}) != len(self.detection):
            raise ValueError('Detection paths must be distinct')
        for case in self.detection:
            if case.path.endswith('.py'):
                ast.parse(case.source)
        for case in self.evidence:
            ast.parse(case.contract)
        return self


def load_corpus():
    data = files('config').joinpath('security_eval_v1.json').read_bytes()
    if len(data) > 256_000:
        raise ValueError('Bundled evaluation corpus exceeds its byte budget')
    return Corpus.model_validate_json(data), hashlib.sha256(data).hexdigest()

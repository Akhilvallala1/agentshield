from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from agentshield.types import Detection

PRESIDIO_TO_LABEL = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "US_SSN": "SSN",
    "CREDIT_CARD": "CREDIT_CARD",
}


class PresidioNER:
    def __init__(self, score_threshold: float = 0.4):
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        self._analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self._threshold = score_threshold
        self._cache: dict[str, list[Detection]] = {}

    def __call__(self, text: str) -> list[Detection]:
        if text not in self._cache:
            results = self._analyzer.analyze(text=text, language="en", entities=list(PRESIDIO_TO_LABEL),
                                             score_threshold=self._threshold)
            self._cache[text] = [Detection(PRESIDIO_TO_LABEL[r.entity_type], r.start, r.end, "L2") for r in results]
        return self._cache[text]


@lru_cache
def get_ner() -> PresidioNER:
    return PresidioNER()

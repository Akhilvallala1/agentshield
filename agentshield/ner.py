import logging
from collections import OrderedDict
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from agentshield.types import Detection

# Presidio logs every skipped non-English recognizer and unmapped spaCy label; only errors matter here.
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

PRESIDIO_TO_LABEL = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "US_SSN": "SSN",
    "CREDIT_CARD": "CREDIT_CARD",
}


class PresidioNER:
    def __init__(self, score_threshold: float = 0.4, cache_size: int = 4096):
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        self._analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self._threshold = score_threshold
        self._cache: OrderedDict[str, list[Detection]] = OrderedDict()
        self._cache_size = cache_size  # bounded: cached keys are raw message text (SEC2)

    def __call__(self, text: str) -> list[Detection]:
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        results = self._analyzer.analyze(text=text, language="en", entities=list(PRESIDIO_TO_LABEL),
                                         score_threshold=self._threshold)
        dets = [Detection(PRESIDIO_TO_LABEL[r.entity_type], r.start, r.end, "L2") for r in results]
        self._cache[text] = dets
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return dets


@lru_cache
def get_ner() -> PresidioNER:
    return PresidioNER()

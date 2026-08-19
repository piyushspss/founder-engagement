from app.normalize.config import Config, load_config
from app.normalize.dedup import classify_pair, find_duplicates
from app.normalize.normalizer import normalize, normalize_corpus

__all__ = ["Config", "load_config", "normalize", "normalize_corpus",
           "find_duplicates", "classify_pair"]

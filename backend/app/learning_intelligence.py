import csv
import os
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any
from io import StringIO

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split

try:
    from transformers import pipeline as hf_pipeline
except Exception:
    hf_pipeline = None

ML_DATA_DIR = Path(__file__).parent.parent / "data" / "ml"
SENTIMENT_DATASET_PATH = ML_DATA_DIR / "sentiment_dataset.csv"
TOPIC_CATALOG_PATH = ML_DATA_DIR / "topic_catalog.csv"


class LearningIntelligenceService:
    """Sentiment analysis + content-based recommendations for EduBot."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._initialized = False

        self._sentiment_vectorizer: TfidfVectorizer | None = None
        self._sentiment_model: LogisticRegression | None = None

        self._topic_vectorizer: TfidfVectorizer | None = None
        self._topic_matrix = None
        self._topics: list[dict[str, str]] = []
        self._hf_sentiment = None
        self._hf_model_name = os.getenv(
            "BERT_SENTIMENT_MODEL",
            "cardiffnlp/twitter-roberta-base-sentiment-latest",
        )
        self._use_hf_sentiment = os.getenv("USE_BERT_SENTIMENT", "false").lower() in {"1", "true", "yes"}

        self._metrics: dict[str, Any] = {
            "status": "not_initialized",
        }

    def initialize(self) -> None:
        """Train/load models once."""
        with self._lock:
            if self._initialized:
                return

            self._train_sentiment_model()
            self._prepare_recommender()
            self._try_init_hf_sentiment()

            self._initialized = True
            self._metrics["status"] = "ready"

    def _try_init_hf_sentiment(self) -> None:
        if not self._use_hf_sentiment:
            self._metrics["hf_sentiment"] = "disabled"
            return
        if hf_pipeline is None:
            self._metrics["hf_sentiment"] = "transformers_not_installed"
            return
        try:
            self._hf_sentiment = hf_pipeline("sentiment-analysis", model=self._hf_model_name)
            self._metrics["hf_sentiment"] = f"enabled:{self._hf_model_name}"
        except Exception as exc:
            self._hf_sentiment = None
            self._metrics["hf_sentiment"] = f"init_failed:{exc}"

    def _train_sentiment_model(self) -> None:
        rows = self._read_csv(SENTIMENT_DATASET_PATH)
        if not rows:
            raise RuntimeError(f"Sentiment dataset is missing or empty: {SENTIMENT_DATASET_PATH}")

        # Support both formats:
        # 1) text,label
        # 2) textID,text,sentiment,Time of Tweet,...
        texts: list[str] = []
        labels: list[str] = []
        for row in rows:
            text = (row.get("text") or "").strip()
            label = (row.get("label") or row.get("sentiment") or "").strip().lower()
            if not text or not label:
                continue
            if label not in {"positive", "negative", "neutral"}:
                continue
            texts.append(text)
            labels.append(label)

        if len(texts) < 6:
            raise RuntimeError("Sentiment dataset is too small. Add at least 6 labeled rows.")

        sentiment_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        X = sentiment_vectorizer.fit_transform(texts)

        label_counts = Counter(labels)
        can_stratify = len(label_counts) > 1 and min(label_counts.values()) > 1

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            labels,
            test_size=0.2,
            random_state=42,
            stratify=labels if can_stratify else None,
        )

        sentiment_model = LogisticRegression(max_iter=1200)
        sentiment_model.fit(X_train, y_train)

        y_pred = sentiment_model.predict(X_test)
        accuracy = float(accuracy_score(y_test, y_pred))
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        self._sentiment_vectorizer = sentiment_vectorizer
        self._sentiment_model = sentiment_model
        self._metrics.update(
            {
                "sentiment_accuracy": round(accuracy, 4),
                "sentiment_train_size": len(y_train),
                "sentiment_test_size": len(y_test),
                "sentiment_label_distribution": dict(label_counts),
                "sentiment_report": report,
                "sentiment_dataset_path": str(SENTIMENT_DATASET_PATH),
            }
        )

    def _prepare_recommender(self) -> None:
        rows = self._read_csv(TOPIC_CATALOG_PATH)
        if not rows:
            raise RuntimeError(f"Topic catalog is missing or empty: {TOPIC_CATALOG_PATH}")

        topics = []
        corpus = []
        for row in rows:
            # Support both formats:
            # 1) topic,description
            # 2) Category,Topic,Description
            topic = (row.get("topic") or row.get("Topic") or "").strip()
            description = (row.get("description") or row.get("Description") or "").strip()
            if not topic:
                continue
            topics.append({"topic": topic, "description": description})
            corpus.append(f"{topic}. {description}")

        if not topics:
            raise RuntimeError("Topic catalog has no valid topic rows.")

        topic_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        topic_matrix = topic_vectorizer.fit_transform(corpus)

        self._topics = topics
        self._topic_vectorizer = topic_vectorizer
        self._topic_matrix = topic_matrix
        self._metrics.update(
            {
                "topic_count": len(topics),
                "topic_dataset_path": str(TOPIC_CATALOG_PATH),
            }
        )

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                with path.open("r", encoding=encoding, newline="") as f:
                    return list(csv.DictReader(f))
            except UnicodeDecodeError:
                continue

        # Last resort: decode with replacement so a single bad byte does not block training.
        raw = path.read_bytes()
        decoded = raw.decode("latin-1", errors="replace")
        return list(csv.DictReader(StringIO(decoded)))

    def analyze_sentiment(self, text: str) -> dict[str, Any]:
        self.initialize()

        if self._hf_sentiment is not None:
            try:
                out = self._hf_sentiment(text)[0]
                raw_label = str(out.get("label", "neutral")).lower()
                score = float(out.get("score", 0.0))

                if "neg" in raw_label or raw_label in {"label_0"}:
                    label = "negative"
                elif "pos" in raw_label or raw_label in {"label_2"}:
                    label = "positive"
                else:
                    label = "neutral"

                tone_map = {
                    "negative": "frustrated",
                    "positive": "confident",
                    "neutral": "neutral",
                }
                guidance_map = {
                    "negative": "I will keep answers step-by-step and concise.",
                    "positive": "I can include challenge questions after the answer.",
                    "neutral": "I will provide a balanced explanation with examples.",
                }

                return {
                    "label": label,
                    "emotion": tone_map.get(label, "neutral"),
                    "confidence": round(score, 4),
                    "guidance": guidance_map.get(label, guidance_map["neutral"]),
                    "engine": "hf_transformers",
                }
            except Exception:
                # Fall back to local model on any inference error.
                pass

        assert self._sentiment_model is not None
        assert self._sentiment_vectorizer is not None

        vector = self._sentiment_vectorizer.transform([text])
        label = str(self._sentiment_model.predict(vector)[0]).lower()
        probabilities = self._sentiment_model.predict_proba(vector)[0]
        confidence = float(max(probabilities))

        tone_map = {
            "negative": "frustrated",
            "positive": "confident",
            "neutral": "neutral",
        }
        guidance_map = {
            "negative": "I will keep answers step-by-step and concise.",
            "positive": "I can include challenge questions after the answer.",
            "neutral": "I will provide a balanced explanation with examples.",
        }

        return {
            "label": label,
            "emotion": tone_map.get(label, "neutral"),
            "confidence": round(confidence, 4),
            "guidance": guidance_map.get(label, guidance_map["neutral"]),
            "engine": "logistic_regression",
        }

    def recommend_topics(self, user_text: str, top_k: int = 3) -> list[dict[str, Any]]:
        self.initialize()
        if not user_text.strip():
            return []

        assert self._topic_vectorizer is not None
        assert self._topic_matrix is not None

        query_vec = self._topic_vectorizer.transform([user_text])
        scores = cosine_similarity(query_vec, self._topic_matrix)[0]

        ranked_indices = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)
        recommendations: list[dict[str, Any]] = []

        for idx in ranked_indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            topic = self._topics[idx]
            recommendations.append(
                {
                    "topic": topic["topic"],
                    "description": topic["description"],
                    "score": round(score, 4),
                }
            )
            if len(recommendations) >= top_k:
                break

        return recommendations

    def build_support_block(self, user_text: str) -> str:
        sentiment = self.analyze_sentiment(user_text)
        recommendations = self.recommend_topics(user_text, top_k=3)

        lines = [
            "",
            "---",
            "Learning Support:",
            f"- Sentiment: {sentiment['emotion']} ({sentiment['label']}, confidence {sentiment['confidence']})",
            f"- Adaptive mode: {sentiment['guidance']}",
        ]

        if recommendations:
            lines.append("- Recommended next topics:")
            for rec in recommendations:
                lines.append(f"  - {rec['topic']} ({rec['score']})")

        return "\n".join(lines)

    def get_metrics(self) -> dict[str, Any]:
        self.initialize()
        return self._metrics.copy()

    def get_dataset_sources(self) -> list[dict[str, str]]:
        return [
            {
                "name": "TweetEval Sentiment",
                "url": "https://huggingface.co/datasets/tweet_eval",
                "target_path": "backend/data/ml/sentiment_dataset.csv",
                "note": "Use this dataset to expand sentiment labels (positive/negative/neutral).",
            },
            {
                "name": "GoEmotions",
                "url": "https://huggingface.co/datasets/google-research-datasets/go_emotions",
                "target_path": "backend/data/ml/sentiment_dataset.csv",
                "note": "Optional for richer emotion coverage before mapping to 3 classes.",
            },
            {
                "name": "Custom Topic Catalog",
                "url": "https://en.wikipedia.org/wiki/List_of_computer_science_topics",
                "target_path": "backend/data/ml/topic_catalog.csv",
                "note": "Maintain your own syllabus topics and descriptions for recommendations.",
            },
        ]


learning_intelligence = LearningIntelligenceService()

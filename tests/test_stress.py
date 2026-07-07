"""
tests/test_stress.py
Stress tests for the NLP pipeline.

Tests:
1. Throughput: how many resumes can we parse per second
2. Memory: embedding 100+ candidates doesn't leak memory
3. Concurrency: parser is safe under concurrent requests
4. Large text: handles very long resumes without crashing
5. Edge cases: empty files, binary garbage, unicode, special characters

Run:
    pytest tests/test_stress.py -v                    # all stress tests
    pytest tests/test_stress.py -v -k "throughput"   # just throughput
    pytest tests/test_stress.py -v --timeout=120     # with longer timeout

Note: These tests are slower by design. They measure real performance.
"""
import time
import threading
import pytest
import logging

logger = logging.getLogger(__name__)

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_RESUME = """
Jane Doe
jane.doe@example.com
(555) 987-6543
US Citizen — Green Card Holder

SUMMARY
Senior Software Engineer with 8 years of experience building scalable
distributed systems on AWS. Expert in Python, Java, and Kubernetes.

EXPERIENCE

Senior Software Engineer — TechCorp Inc
Jan 2020 – Present
• Led migration from monolith to microservices using Docker and Kubernetes
• Built data pipelines with Apache Kafka and Apache Spark
• Mentored team of 5 junior engineers

Software Engineer — StartupXYZ
Mar 2016 – Dec 2019
• Developed REST APIs using Python FastAPI and PostgreSQL
• Implemented CI/CD pipelines with GitHub Actions
• Optimised SQL queries reducing p99 latency by 40%

SKILLS
Python, Java, JavaScript, TypeScript, React, Node.js,
AWS, Azure, Docker, Kubernetes, Terraform, PostgreSQL,
MongoDB, Redis, Apache Kafka, Apache Spark, FastAPI,
Machine Learning, scikit-learn, TensorFlow, Git, Linux

EDUCATION
B.S. Computer Science — MIT — 2016
"""

LARGE_RESUME = SAMPLE_RESUME * 10  # ~7000 chars, tests truncation handling

UNICODE_RESUME = """
Müller, André
andre.muller@beispiel.de
软件工程师 — H1B Visa
2018 – Present: Python Developer
Skills: Python, AWS, Docker, PostgreSQL, React
经验: 6 years of experience in software development
"""

EDGE_CASES = [
    ("empty",     b"",                               "pdf"),
    ("whitespace",b"   \n\n   ",                     "pdf"),
    ("binary",    bytes(range(256)),                  "pdf"),
]


# ── Parser throughput tests ───────────────────────────────────────────────────

class TestParserThroughput:

    def _make_simple_pdf(self, text: str) -> bytes:
        """Create minimal PDF for testing."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            import io
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=letter)
            y = 750
            for line in text.split("\n")[:40]:
                c.drawString(50, y, line.strip()[:80])
                y -= 15
                if y < 50:
                    break
            c.save()
            return buf.getvalue()
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_parse_10_resumes_under_30_seconds(self):
        """10 resumes should parse in under 30 seconds on any machine."""
        from ml.parser import parse_resume

        pdf = self._make_simple_pdf(SAMPLE_RESUME)
        start = time.perf_counter()

        results = []
        for i in range(10):
            result = parse_resume(pdf, "pdf")
            results.append(result)

        elapsed = time.perf_counter() - start

        assert len(results) == 10
        assert all(r["visa_status"] == "citizen" for r in results)
        assert elapsed < 30.0, f"Parsing 10 resumes took {elapsed:.1f}s (limit: 30s)"

        rate = 10 / elapsed
        logger.info(f"[stress] Parse throughput: {rate:.1f} resumes/sec")
        print(f"\n[stress] Parse throughput: {rate:.1f} resumes/sec ({elapsed:.2f}s for 10)")

    def test_parse_large_resume(self):
        """Parser should handle very long resumes without crashing."""
        from ml.parser import parse_resume

        pdf = self._make_simple_pdf(LARGE_RESUME)
        start = time.perf_counter()
        result = parse_resume(pdf, "pdf")
        elapsed = time.perf_counter() - start

        assert result["raw_text"] is not None
        assert len(result["skills"]) > 0
        assert elapsed < 10.0, f"Large resume took {elapsed:.1f}s (limit: 10s)"
        print(f"\n[stress] Large resume parsed in {elapsed:.2f}s")

    def test_parse_unicode_resume(self):
        """Parser should handle unicode characters gracefully."""
        from ml.parser import parse_resume

        pdf = self._make_simple_pdf(UNICODE_RESUME)
        result = parse_resume(pdf, "pdf")

        assert result is not None
        assert result["visa_status"] == "h1b"
        assert "Python" in result["skills"]
        print(f"\n[stress] Unicode resume: skills={result['skills']}")


# ── Embedding throughput tests ────────────────────────────────────────────────

class TestEmbedderThroughput:

    def test_embed_100_texts_under_60_seconds(self):
        """Batch embedding 100 texts should complete under 60s on CPU."""
        from ml.embedder import embed_texts_batch, EMBEDDING_DIM

        texts = [f"Software engineer {i} with Python AWS Docker experience" for i in range(100)]

        start = time.perf_counter()
        results = embed_texts_batch(texts, batch_size=32)
        elapsed = time.perf_counter() - start

        assert len(results) == 100
        assert all(len(v) == EMBEDDING_DIM for v in results)
        assert elapsed < 60.0, f"Embedding 100 texts took {elapsed:.1f}s (limit: 60s)"

        rate = 100 / elapsed
        logger.info(f"[stress] Embed throughput: {rate:.1f} texts/sec")
        print(f"\n[stress] Embed throughput: {rate:.1f} texts/sec ({elapsed:.2f}s for 100)")

    def test_embed_single_text_under_1_second(self):
        """Single embedding should complete in under 1 second (after model loaded)."""
        from ml.embedder import embed_text

        # Warm up
        embed_text("warm up")

        # Measure
        times = []
        for _ in range(10):
            start = time.perf_counter()
            embed_text("Python developer with 5 years experience in AWS and Docker")
            times.append(time.perf_counter() - start)

        avg_ms = sum(times) / len(times) * 1000
        max_ms = max(times) * 1000
        print(f"\n[stress] Single embed: avg={avg_ms:.1f}ms, max={max_ms:.1f}ms")
        assert max_ms < 1000, f"Single embed max was {max_ms:.1f}ms (limit: 1000ms)"

    def test_memory_stable_over_repeated_embeds(self):
        """Memory should not grow significantly over 200 embed calls."""
        try:
            import psutil
            import os
        except ImportError:
            pytest.skip("psutil not installed — pip install psutil")

        from ml.embedder import embed_text

        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB

        for i in range(200):
            embed_text(f"Candidate {i} with Python and AWS skills and {i} years experience")

        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        growth = mem_after - mem_before

        print(f"\n[stress] Memory before: {mem_before:.1f}MB, after: {mem_after:.1f}MB, growth: {growth:.1f}MB")
        assert growth < 200, f"Memory grew by {growth:.1f}MB over 200 embeds (limit: 200MB)"


# ── Concurrency tests ─────────────────────────────────────────────────────────

class TestConcurrency:

    def test_embedder_thread_safe(self):
        """
        Embedding model should be safe to call from multiple threads.
        (Streamlit can have multiple user sessions.)
        """
        from ml.embedder import embed_text, EMBEDDING_DIM

        results = []
        errors = []
        lock = threading.Lock()

        def embed_worker(text: str):
            try:
                vec = embed_text(text)
                with lock:
                    results.append(vec)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        texts = [f"Candidate {i} Python AWS Docker" for i in range(20)]
        threads = [threading.Thread(target=embed_worker, args=(t,)) for t in texts]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.perf_counter() - start

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 20
        assert all(len(v) == EMBEDDING_DIM for v in results)
        print(f"\n[stress] 20 concurrent embeds in {elapsed:.2f}s")

    def test_parser_thread_safe(self):
        """Parser should be safe under concurrent use."""
        from ml.parser import extract_skills, extract_visa_status
        import spacy

        nlp = spacy.blank("en")
        results = []
        errors = []
        lock = threading.Lock()

        def parse_worker(i: int):
            try:
                text = f"Developer {i} with Python AWS Docker H1B visa 2019-2023"
                skills = extract_skills(text, nlp)
                visa = extract_visa_status(text)
                with lock:
                    results.append({"skills": skills, "visa": visa})
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=parse_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 20
        assert all(r["visa"] == "h1b" for r in results)


# ── Edge case stress tests ────────────────────────────────────────────────────

class TestEdgeCases:

    def test_skill_extraction_on_very_long_text(self):
        """Skill extractor should handle 10KB text without performance degradation."""
        from ml.parser import extract_skills
        import spacy

        nlp = spacy.blank("en")
        long_text = ("Python developer with AWS and Docker experience. " * 200)

        start = time.perf_counter()
        skills = extract_skills(long_text, nlp)
        elapsed = time.perf_counter() - start

        assert "Python" in skills
        assert elapsed < 5.0, f"Skill extraction on long text took {elapsed:.1f}s"

    def test_yoe_extraction_with_many_dates(self):
        """YOE extractor should handle resumes with many date ranges."""
        from ml.parser import extract_yoe

        many_dates = "\n".join([
            f"Company {i}: Jan {2000 + i} - Dec {2001 + i}" for i in range(20)
        ])
        start = time.perf_counter()
        yoe = extract_yoe(many_dates)
        elapsed = time.perf_counter() - start

        assert yoe >= 0
        assert elapsed < 2.0, f"YOE extraction with many dates took {elapsed:.1f}s"

    def test_embed_text_with_special_characters(self):
        """Embedder should handle special characters and emoji without crashing."""
        from ml.embedder import embed_text, EMBEDDING_DIM

        special = "Python dev 🐍 | AWS ☁️ | C++ & C# | $100/hr | 100% remote"
        vec = embed_text(special)
        assert len(vec) == EMBEDDING_DIM

    def test_embed_very_long_text_truncated(self):
        """Very long text should be truncated and embedded without error."""
        from ml.embedder import embed_text, EMBEDDING_DIM

        long_text = "Python developer with AWS experience. " * 500  # ~20KB
        vec = embed_text(long_text)
        assert len(vec) == EMBEDDING_DIM


# ── Performance stats test ────────────────────────────────────────────────────

class TestPerformanceTracking:

    def test_timed_decorator_records_stats(self):
        from ml.performance import timed, get_pipeline_stats, reset_stats

        reset_stats()

        @timed("test_operation")
        def slow_function():
            time.sleep(0.01)
            return "done"

        for _ in range(5):
            slow_function()

        stats = get_pipeline_stats()
        assert "test_operation" in stats
        assert stats["test_operation"]["calls"] == 5
        assert stats["test_operation"]["avg_ms"] >= 10
        assert stats["test_operation"]["max_ms"] >= 10

    def test_warm_up_completes_without_error(self):
        from ml.performance import warm_up_models
        elapsed = warm_up_models()
        assert elapsed > 0
        print(f"\n[stress] Model warm-up: {elapsed:.2f}s")

    def test_recommended_batch_size_is_reasonable(self):
        from ml.performance import recommended_batch_size
        size = recommended_batch_size()
        assert 8 <= size <= 128
        print(f"\n[stress] Recommended batch size: {size}")

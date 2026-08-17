import re
import hashlib
import math
from collections import Counter
from typing import List, Dict, Any, Tuple
from models import SearchResult, ErrorRecord, Solution

class KBEngine:
    """
    Error Normalization Engine, Similarity Scoring, and Agent Context Generator.
    """

    @staticmethod
    def normalize_error(text: str) -> str:
        """
        Normalizes stack trace or error message by removing dynamic execution artifacts:
        - File system paths -> <PATH>
        - Line numbers -> <NUM>
        - Memory hex addresses -> <HEX_ADDR>
        - UUIDs / Hashes -> <HASH>
        - Timestamps -> <TIMESTAMP>
        - Process IDs -> <PID>
        """
        if not text:
            return ""

        s = text

        # 1. Normalize timestamps
        s = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?', '<TIMESTAMP>', s)
        s = re.sub(r'\d{2}:\d{2}:\d{2}(?:\.\d+)?', '<TIMESTAMP>', s)

        # 2. Normalize memory addresses (0x7f8a9b...)
        s = re.sub(r'0x[0-9a-fA-F]{4,16}\b', '<HEX_ADDR>', s)

        # 3. Normalize UUIDs
        s = re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', '<HASH>', s)

        # 4. Normalize file paths (Unix and Windows paths)
        # Matches /path/to/file.ext or C:\path\to\file.ext
        s = re.sub(r'(?:[a-zA-Z]:\\|/)[^\s:\'",\(\)]+(?:/[^\s:\'",\(\)]+|\\[^\s:\'",\(\)]+)*', '<PATH>', s)

        # 5. Normalize line numbers in stack traces (e.g. line 42, :42:, line 105, col 12)
        s = re.sub(r'\bline\s+\d+\b', 'line <NUM>', s, flags=re.IGNORECASE)
        s = re.sub(r'::?\d+(?::\d+)?\b', ':<NUM>', s)
        s = re.sub(r',?\s*col(?:umn)?\s+\d+\b', '', s, flags=re.IGNORECASE)

        # 6. Normalize process/thread IDs (e.g. pid=12345, [PID 999])
        s = re.sub(r'\b(?:pid|PID|process)\s*[:=]?\s*\d+\b', '<PID>', s)

        # 7. Clean repeated whitespace & trim lines
        lines = [line.strip() for line in s.splitlines()]
        cleaned = "\n".join([line for line in lines if line])
        return cleaned.strip()

    @staticmethod
    def compute_fingerprint(normalized_trace: str, error_type: str = "") -> str:
        """
        Computes SHA-256 fingerprint from normalized error trace and error type.
        """
        raw = f"{error_type.strip().lower()}:{normalized_trace.strip().lower()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """
        Tokenizes text into words and identifier tokens.
        """
        words = re.findall(r'\b[a-zA-Z0-9_\-\.]+\b', text.lower())
        return [w for w in words if len(w) > 1]

    @classmethod
    def calculate_token_similarity(cls, text1: str, text2: str) -> float:
        """
        Calculates hybrid similarity score combining TF-IDF style token cosine similarity
        and character 3-gram Jaccard index.
        """
        tokens1 = cls.tokenize(text1)
        tokens2 = cls.tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        # Word Token Cosine Similarity
        vec1 = Counter(tokens1)
        vec2 = Counter(tokens2)
        intersection = set(vec1.keys()) & set(vec2.keys())
        dot_product = sum(vec1[x] * vec2[x] for x in intersection)

        sum1 = sum(v ** 2 for v in vec1.values())
        sum2 = sum(v ** 2 for v in vec2.values())
        magnitude = math.sqrt(sum1) * math.sqrt(sum2)

        cosine_sim = (dot_product / magnitude) if magnitude else 0.0

        # Character 3-gram Jaccard Similarity for fuzzy matching
        ngrams1 = set(text1[i:i+3].lower() for i in range(len(text1) - 2))
        ngrams2 = set(text2[i:i+3].lower() for i in range(len(text2) - 2))

        if not ngrams1 or not ngrams2:
            ngram_sim = 0.0
        else:
            ngram_sim = len(ngrams1 & ngrams2) / float(len(ngrams1 | ngrams2))

        # Weighted combination
        final_score = 0.6 * cosine_sim + 0.4 * ngram_sim
        return round(min(max(final_score, 0.0), 1.0), 4)

    @staticmethod
    def format_markdown_context(results: List[SearchResult]) -> str:
        """
        Formats search results into Markdown context suitable for AI agent context window.
        """
        if not results:
            return "### AI Agent Knowledge Base Context\nNo matching error solutions found."

        md_output = ["# 🧠 AI Agent Error Knowledge Base Context\n"]
        md_output.append(f"Found **{len(results)} matching records** for your issue:\n")

        for idx, res in enumerate(results, 1):
            score_pct = int(res.confidence_score * 100)
            rec = res.record
            sol = res.matched_solution

            md_output.append(f"---")
            md_output.append(f"## Solution #{idx}: `{rec.error_type}` (Match Confidence: {score_pct}%, Match Type: `{res.match_type}`)")
            if rec.tags:
                tags_str = " ".join([f"`#{t}`" for t in rec.tags])
                md_output.append(f"**Tags**: {tags_str}")
            
            md_output.append(f"\n### 🔍 Root Cause")
            md_output.append(sol.cause)

            md_output.append(f"\n### 🛠️ Patch / Fix")
            md_output.append(f"```bash\n{sol.patch_or_fix}\n```")

            if sol.explanation:
                md_output.append(f"\n### 💡 Explanation")
                md_output.append(sol.explanation)

            md_output.append(f"\n**Verification Rating**: ⭐ {sol.verification_score}/5.0 (Applied {sol.verified_count} times)\n")

        return "\n".join(md_output)

    @staticmethod
    def format_json_context(results: List[SearchResult]) -> Dict[str, Any]:
        """
        Formats search results into a structured JSON payload for agents.
        """
        return {
            "total_matches": len(results),
            "matches": [
                {
                    "rank": i + 1,
                    "confidence_score": res.confidence_score,
                    "match_type": res.match_type,
                    "error_type": res.record.error_type,
                    "error_message": res.record.error_message,
                    "tags": res.record.tags,
                    "cause": res.matched_solution.cause,
                    "patch_or_fix": res.matched_solution.patch_or_fix,
                    "explanation": res.matched_solution.explanation,
                    "verification_score": res.matched_solution.verification_score
                }
                for i, res in enumerate(results)
            ]
        }

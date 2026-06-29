"""
Advanced NLP Content Analysis
Second-pass deep analysis using NLP libraries
Runs in parallel with heuristic scoring
"""
import re
from typing import Dict, Tuple, Optional
from bs4 import BeautifulSoup
import extruct
from urllib.parse import urlparse
import tldextract
import textstat
import ftfy
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import hashlib


class NLPAnalyzer:
    """Advanced NLP-based content analysis"""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=500, stop_words='english')

        # Known wire service patterns for dedup
        self.wire_patterns = {
            'reuters': ['(Reuters)', 'Reporting by', 'Editing by'],
            'ap': ['(AP)', 'Associated Press', 'The Associated Press'],
            'bloomberg': ['(Bloomberg)', 'Bloomberg News'],
            'afp': ['(AFP)', 'Agence France-Presse']
        }

    def analyze_content(self, html: str, url: str, extracted_text: str, title: str) -> Dict:
        """
        Comprehensive NLP analysis
        Returns dict with all analysis results
        """
        analysis = {}

        # 1. Extract structured data (schema.org, OpenGraph, JSON-LD)
        structured_data = self._extract_structured_data(html)
        analysis['structured_data'] = structured_data

        # 2. Domain analysis
        domain_info = self._analyze_domain(url)
        analysis['domain'] = domain_info

        # 3. Text quality metrics
        quality_metrics = self._analyze_text_quality(extracted_text)
        analysis['quality_metrics'] = quality_metrics

        # 4. Title quality
        title_quality = self._analyze_title(title)
        analysis['title_quality'] = title_quality

        # 5. Wire service detection
        wire_detection = self._detect_wire_service(extracted_text)
        analysis['wire_service'] = wire_detection

        # 6. Content fingerprint for deduplication
        fingerprint = self._generate_fingerprint(extracted_text)
        analysis['fingerprint'] = fingerprint

        # 7. Readability scores
        readability = self._calculate_readability(extracted_text)
        analysis['readability'] = readability

        # Calculate aggregate NLP score
        nlp_score = self._calculate_nlp_score(analysis)
        analysis['nlp_score'] = nlp_score

        return analysis

    def _extract_structured_data(self, html: str) -> Dict:
        """Extract schema.org, OpenGraph, JSON-LD using extruct"""
        try:
            metadata = extruct.extract(html, syntaxes=['json-ld', 'opengraph', 'microdata'])

            result = {
                'has_jsonld': bool(metadata.get('json-ld')),
                'has_opengraph': bool(metadata.get('opengraph')),
                'has_microdata': bool(metadata.get('microdata')),
                'article_type': None,
                'author': None,
                'date_published': None
            }

            # Extract article metadata from JSON-LD
            if metadata.get('json-ld'):
                for item in metadata['json-ld']:
                    if isinstance(item, dict):
                        item_type = item.get('@type', '')
                        if 'Article' in str(item_type) or 'NewsArticle' in str(item_type):
                            result['article_type'] = str(item_type)
                            result['author'] = item.get('author', {}).get('name') if isinstance(item.get('author'), dict) else item.get('author')
                            result['date_published'] = item.get('datePublished')

            # Fallback to OpenGraph
            if not result['author'] and metadata.get('opengraph'):
                for og in metadata['opengraph']:
                    if og.get('namespace', {}).get('og') == 'http://ogp.me/ns#':
                        result['author'] = og.get('properties', {}).get('og:article:author')
                        result['date_published'] = og.get('properties', {}).get('og:article:published_time')

            return result
        except Exception as e:
            return {
                'has_jsonld': False,
                'has_opengraph': False,
                'has_microdata': False,
                'error': str(e)
            }

    def _analyze_domain(self, url: str) -> Dict:
        """Analyze domain quality using tldextract"""
        try:
            parsed = urlparse(url)
            extracted = tldextract.extract(url)

            # Check if domain looks like news/journalism
            news_indicators = ['news', 'post', 'times', 'journal', 'tribune', 'herald', 'gazette', 'daily']
            is_news_domain = any(indicator in extracted.domain.lower() for indicator in news_indicators)

            # Check for suspicious patterns
            suspicious_patterns = ['promo', 'deals', 'buy', 'shop', 'discount', 'cheap']
            is_suspicious = any(pattern in extracted.domain.lower() for pattern in suspicious_patterns)

            return {
                'domain': extracted.domain,
                'subdomain': extracted.subdomain,
                'suffix': extracted.suffix,
                'is_news_domain': is_news_domain,
                'is_suspicious': is_suspicious,
                'has_subdomain': bool(extracted.subdomain and extracted.subdomain != 'www')
            }
        except Exception as e:
            return {'error': str(e)}

    def _analyze_text_quality(self, text: str) -> Dict:
        """Analyze text quality using textstat"""
        if not text or len(text) < 100:
            return {
                'error': 'Text too short',
                'automated_readability_index': 0,
                'flesch_reading_ease': 0,
                'lexicon_count': 0
            }

        try:
            return {
                'automated_readability_index': textstat.automated_readability_index(text),
                'flesch_reading_ease': textstat.flesch_reading_ease(text),
                'flesch_kincaid_grade': textstat.flesch_kincaid_grade(text),
                'gunning_fog': textstat.gunning_fog(text),
                'lexicon_count': textstat.lexicon_count(text, removepunct=True),
                'sentence_count': textstat.sentence_count(text),
                'syllable_count': textstat.syllable_count(text),
                'difficult_words': textstat.difficult_words(text)
            }
        except Exception as e:
            return {'error': str(e)}

    def _analyze_title(self, title: str) -> Dict:
        """Analyze title quality using ftfy for cleaning"""
        if not title:
            return {'error': 'No title'}

        # Fix encoding issues
        clean_title = ftfy.fix_text(title)

        # Check for all caps
        is_all_caps = clean_title.isupper() and len(clean_title) > 10

        # Check for clickbait patterns
        clickbait_patterns = [
            r'you won\'t believe',
            r'shocking',
            r'what happened next',
            r'number \d+ will',
            r'doctors hate',
            r'\d+ tricks',
            r'this one weird'
        ]
        clickbait_score = sum(1 for pattern in clickbait_patterns if re.search(pattern, clean_title.lower()))

        # Check for excessive punctuation
        punct_count = sum(1 for c in clean_title if c in '!?')
        excessive_punct = punct_count > 2

        return {
            'original': title,
            'cleaned': clean_title,
            'is_all_caps': is_all_caps,
            'clickbait_score': clickbait_score,
            'excessive_punctuation': excessive_punct,
            'length': len(clean_title),
            'word_count': len(clean_title.split())
        }

    def _detect_wire_service(self, text: str) -> Dict:
        """Detect if content is from wire service"""
        if not text:
            return {'is_wire': False}

        # Check first 500 chars for attribution
        sample = text[:500]

        detected = []
        for wire_name, patterns in self.wire_patterns.items():
            for pattern in patterns:
                if pattern.lower() in sample.lower():
                    detected.append(wire_name)
                    break

        return {
            'is_wire': bool(detected),
            'wire_services': detected,
            'confidence': len(detected) / len(self.wire_patterns) if detected else 0
        }

    def _generate_fingerprint(self, text: str) -> Dict:
        """Generate content fingerprint for deduplication"""
        if not text or len(text) < 100:
            return {'error': 'Text too short'}

        try:
            # Simple hash-based fingerprint
            content_hash = hashlib.md5(text.encode()).hexdigest()

            # Shingling for near-duplicate detection
            # Create 5-word shingles
            words = text.lower().split()
            shingles = set()
            for i in range(len(words) - 4):
                shingle = ' '.join(words[i:i+5])
                shingles.add(shingle)

            # Simhash-like approach (simplified)
            shingle_hashes = [hash(s) % (2**16) for s in list(shingles)[:100]]  # Sample first 100

            return {
                'content_hash': content_hash,
                'shingle_count': len(shingles),
                'shingle_sample': shingle_hashes[:10],  # First 10 for comparison
                'word_count': len(words)
            }
        except Exception as e:
            return {'error': str(e)}

    def _calculate_readability(self, text: str) -> Dict:
        """Calculate readability scores"""
        if not text or len(text) < 100:
            return {'error': 'Text too short'}

        try:
            flesch_ease = textstat.flesch_reading_ease(text)

            # Interpret Flesch Reading Ease
            if flesch_ease >= 90:
                difficulty = 'very_easy'
            elif flesch_ease >= 80:
                difficulty = 'easy'
            elif flesch_ease >= 70:
                difficulty = 'fairly_easy'
            elif flesch_ease >= 60:
                difficulty = 'standard'
            elif flesch_ease >= 50:
                difficulty = 'fairly_difficult'
            elif flesch_ease >= 30:
                difficulty = 'difficult'
            else:
                difficulty = 'very_difficult'

            return {
                'flesch_reading_ease': flesch_ease,
                'difficulty_level': difficulty,
                'grade_level': textstat.flesch_kincaid_grade(text),
                'is_readable': 30 <= flesch_ease <= 80  # Reasonable range for news
            }
        except Exception as e:
            return {'error': str(e)}

    def _calculate_nlp_score(self, analysis: Dict) -> int:
        """Calculate aggregate NLP quality score (0-100)"""
        score = 50  # Start at neutral

        # Structured data bonus
        structured = analysis.get('structured_data', {})
        if structured.get('has_jsonld'):
            score += 15
        if structured.get('has_opengraph'):
            score += 5
        if structured.get('article_type'):
            score += 10

        # Domain analysis
        domain = analysis.get('domain', {})
        if domain.get('is_news_domain'):
            score += 10
        if domain.get('is_suspicious'):
            score -= 15

        # Title quality
        title_q = analysis.get('title_quality', {})
        if title_q.get('is_all_caps'):
            score -= 10
        if title_q.get('clickbait_score', 0) > 0:
            score -= title_q['clickbait_score'] * 5
        if title_q.get('excessive_punctuation'):
            score -= 5

        # Readability (Smart scoring - don't penalize long professional content)
        readability = analysis.get('readability', {})
        quality = analysis.get('quality_metrics', {})
        if readability.get('is_readable'):
            score += 10
        elif readability.get('difficulty_level') == 'very_difficult':
            # Don't penalize if content is long and substantive
            if quality.get('lexicon_count', 0) > 3000:
                score += 5  # Reward comprehensive professional content
            else:
                score -= 5  # Only penalize short difficult content

        # Wire service (syndicated content)
        wire = analysis.get('wire_service', {})
        if wire.get('is_wire'):
            score -= 10  # Prefer original content

        # Content depth scoring (Tiered bonuses based on word count)
        lexicon = quality.get('lexicon_count', 0)
        if lexicon > 5000:
            score += 20  # Comprehensive long-form content
        elif lexicon > 2000:
            score += 15  # Substantial article
        elif lexicon > 1000:
            score += 10  # Good length
        elif lexicon > 300:
            score += 5   # Acceptable

        # Clamp to 0-100
        return max(0, min(100, score))

    def compare_similarity(self, text1: str, text2: str) -> float:
        """
        Compare similarity between two texts using TF-IDF + cosine
        Returns similarity score 0-1
        """
        if not text1 or not text2:
            return 0.0

        try:
            # Create TF-IDF vectors
            tfidf_matrix = self.vectorizer.fit_transform([text1, text2])

            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            return float(similarity)
        except Exception:
            return 0.0

"""
Content Quality Scoring System
Fast heuristic-based scoring (0-100) to identify legitimate articles
Score >70: Legit article, 40-70: Maybe, <40: Skip
"""
import re
import json
from typing import Dict, Tuple
from urllib.parse import urlparse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


class ContentScorer:
    """Scores web content quality using fast heuristics"""

    def __init__(self):
        # Clickbait patterns
        self.clickbait_patterns = [
            r"you won't believe",
            r"shocking",
            r"what happened next",
            r"this is why",
            r"number \d+ will shock you",
            r"doctors hate",
            r"\b[A-Z]{10,}\b",  # All caps words
        ]

        # Roundup patterns
        self.roundup_patterns = [
            r"top \d+",
            r"\d+ things",
            r"\d+ ways",
            r"\d+ reasons",
            r"roundup",
            r"best of \d{4}",
            r"what you need to know"
        ]

        # Known wire services for duplicate detection
        self.wire_services = [
            'reuters', 'ap news', 'associated press', 'bloomberg',
            'afp', 'agence france-presse'
        ]

        # Affiliate link patterns
        self.affiliate_patterns = [
            r'/go/',
            r'ref=',
            r'utm_',
            r'aff_',
            r'affiliate',
            r'track='
        ]

    def score_content(self, html: str, url: str, extracted_content: Dict) -> Tuple[int, Dict]:
        """
        Score content quality (0-100)
        Returns: (score, details_dict)
        """
        score = 50  # Start with baseline - legitimate content should score at least this
        details = {'baseline': 50}

        soup = BeautifulSoup(html, 'html.parser')

        # Positive signals
        schema_score = self._check_schema_org(soup)
        score += schema_score
        details['schema_org'] = schema_score

        byline_score = self._check_byline(soup)
        score += byline_score
        details['byline'] = byline_score

        date_score = self._check_publication_date(soup)
        score += date_score
        details['publication_date'] = date_score

        canonical_score = self._check_canonical_url(soup, url)
        score += canonical_score
        details['canonical'] = canonical_score

        content_length_score = self._check_content_length(extracted_content)
        score += content_length_score
        details['content_length'] = content_length_score

        quote_score = self._check_quote_density(extracted_content.get('content', ''))
        score += quote_score
        details['quote_density'] = quote_score

        # Simplified uniqueness check (we don't have wire database, so just check for attribution)
        uniqueness_score = self._check_attribution(extracted_content.get('content', ''))
        score += uniqueness_score
        details['uniqueness'] = uniqueness_score

        entity_score = self._check_first_paragraph_entities(extracted_content.get('content', ''))
        score += entity_score
        details['named_entities'] = entity_score

        # Negative signals
        roundup_penalty = self._check_roundup_patterns(extracted_content.get('title', ''))
        score += roundup_penalty
        details['roundup_penalty'] = roundup_penalty

        links_penalty = self._check_external_links(soup, extracted_content.get('content', ''))
        score += links_penalty
        details['links_penalty'] = links_penalty

        pagination_penalty = self._check_pagination(url, soup)
        score += pagination_penalty
        details['pagination_penalty'] = pagination_penalty

        clickbait_penalty = self._check_clickbait(extracted_content.get('title', ''))
        score += clickbait_penalty
        details['clickbait_penalty'] = clickbait_penalty

        domain_penalty = self._check_domain_quality(url)
        score += domain_penalty
        details['domain_penalty'] = domain_penalty

        homepage_penalty = self._check_homepage_or_archive(url, soup, extracted_content)
        score += homepage_penalty
        details['homepage_penalty'] = homepage_penalty

        snippet_penalty = self._check_incomplete_snippets(extracted_content.get('content', ''))
        score += snippet_penalty
        details['snippet_penalty'] = snippet_penalty

        # Clamp score to 0-100
        score = max(0, min(100, score))

        return score, details

    def _check_schema_org(self, soup: BeautifulSoup) -> int:
        """Check for schema.org Article or NewsArticle: +20"""
        # Check JSON-LD scripts
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                if isinstance(data, dict):
                    schema_type = data.get('@type', '')
                    if 'Article' in schema_type or 'NewsArticle' in schema_type:
                        return 20
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            schema_type = item.get('@type', '')
                            if 'Article' in schema_type or 'NewsArticle' in schema_type:
                                return 20
            except:
                continue

        # Also check for og:type meta tag
        og_type = soup.find('meta', property='og:type')
        if og_type and og_type.get('content'):
            if 'article' in og_type['content'].lower():
                return 15  # Slightly lower score than JSON-LD

        return 0

    def _check_byline(self, soup: BeautifulSoup) -> int:
        """Check for author byline: +10"""
        # Look for common byline patterns
        author_selectors = [
            {'class': re.compile(r'author|byline|writer', re.I)},
            {'rel': 'author'},
            {'itemprop': 'author'},
            {'name': 'author'}
        ]

        for selector in author_selectors:
            author_elem = soup.find(['span', 'div', 'p', 'a', 'meta'], selector)
            if author_elem:
                # Try content attribute first (for meta tags)
                author_text = author_elem.get('content', author_elem.get_text()).strip()
                if not author_text:
                    continue
                # Check if it looks like a person name (2-4 words, or just has content)
                words = [w for w in author_text.split() if w]
                if len(words) >= 2:
                    # Less strict - just check if at least one word is capitalized
                    if any(w[0].isupper() for w in words):
                        return 10
        return 0

    def _check_publication_date(self, soup: BeautifulSoup) -> int:
        """Check for recent publication date within 2 years: +10"""
        date_selectors = [
            {'itemprop': 'datePublished'},
            {'property': 'article:published_time'},
            {'name': 'article:published_time'},
            {'name': 'publishdate'},
            {'class': re.compile(r'date|time|publish', re.I)}
        ]

        two_years_ago = datetime.now() - timedelta(days=730)

        for selector in date_selectors:
            date_elem = soup.find(['time', 'span', 'div', 'meta'], selector)
            if date_elem:
                date_str = date_elem.get('datetime') or date_elem.get('content') or date_elem.get_text()
                if not date_str:
                    continue
                try:
                    # Try ISO format first (most common for meta tags)
                    if 'T' in date_str:  # ISO format like 2025-01-01T12:00:00Z
                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('T')[0])
                        if date_obj >= two_years_ago:
                            return 10
                    # Try parsing various date formats
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%d %B %Y', '%Y']:
                        try:
                            date_obj = datetime.strptime(date_str[:10] if len(date_str) > 10 else date_str, fmt)
                            if date_obj >= two_years_ago:
                                return 10
                        except:
                            continue
                except:
                    continue
        return 0

    def _check_canonical_url(self, soup: BeautifulSoup, url: str) -> int:
        """Check for clean canonical URL: +8"""
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            canonical_url = canonical['href']
            parsed_original = urlparse(url)
            parsed_canonical = urlparse(canonical_url)

            # Same domain and not empty
            if parsed_original.netloc == parsed_canonical.netloc and canonical_url:
                return 8
        return 0

    def _check_content_length(self, extracted_content: Dict) -> int:
        """Check content length 600-4,500 words: +12, 4500-20000: +5, else penalize"""
        content = extracted_content.get('content', '')
        word_count = len(content.split())

        if 600 <= word_count <= 4500:
            return 12
        elif 4500 < word_count <= 20000:
            return 5  # Long articles still get bonus (was 0)
        elif word_count < 250 or word_count > 20000:
            return -10
        else:
            return 0  # 250-600 = neutral

    def _check_quote_density(self, content: str) -> int:
        """Check quote density 3-30%: +5"""
        if not content:
            return 0

        sentences = re.split(r'[.!?]+', content)
        total_sentences = len([s for s in sentences if s.strip()])

        if total_sentences == 0:
            return 0

        # Count sentences with quotes
        quoted_sentences = sum(1 for s in sentences if '"' in s or '"' in s or '"' in s or "'" in s or "'" in s)
        quote_density = (quoted_sentences / total_sentences) * 100

        if 3 <= quote_density <= 30:
            return 5
        return 0

    def _check_attribution(self, content: str) -> int:
        """Check if content has wire service attribution: +8 if unique"""
        content_lower = content.lower()

        # If attributed to wire service, likely syndicated
        for wire in self.wire_services:
            if wire in content_lower[:500]:  # Check first 500 chars
                return 0  # Not unique

        return 8  # Appears unique

    def _check_first_paragraph_entities(self, content: str) -> int:
        """Check for named entities in first paragraph: +5"""
        if not content:
            return 0

        # Get first paragraph (first 200 chars or until double newline)
        first_para = content[:200].split('\n\n')[0]

        # Simple heuristic: look for capitalized words that aren't sentence starts
        words = first_para.split()
        capitalized_mid_sentence = 0

        for i, word in enumerate(words):
            if i > 0 and word[0].isupper() and len(word) > 2:
                # Not after period
                if i > 0 and not words[i-1].endswith('.'):
                    capitalized_mid_sentence += 1

        # If we have 2+ proper nouns, likely has named entities
        if capitalized_mid_sentence >= 2:
            return 5
        return 0

    def _check_roundup_patterns(self, title: str) -> int:
        """Check for roundup patterns: -5 (reduced from -10)"""
        title_lower = title.lower()

        for pattern in self.roundup_patterns:
            if re.search(pattern, title_lower):
                return -5  # Reduced penalty

        # Check for excessive bullet points in title
        if title.count('•') > 2 or title.count('|') > 2:
            return -5  # Reduced penalty

        return 0

    def _check_external_links(self, soup: BeautifulSoup, content: str) -> int:
        """Check for excessive external links: -6 (reduced from -12)"""
        if not content:
            return 0

        # Count external links in body
        body = soup.find(['article', 'main', 'body']) or soup
        links = body.find_all('a', href=True)
        external_links = 0
        affiliate_links = 0

        for link in links:
            href = link.get('href', '')
            # Check if affiliate
            for pattern in self.affiliate_patterns:
                if re.search(pattern, href):
                    affiliate_links += 1
                    break
            external_links += 1

        word_count = len(content.split())
        words_per_300 = max(1, word_count // 300)

        # Penalty if >50 external links (increased from 20) OR >2 affiliate per 300 words (increased from 1)
        if external_links > 50 or (affiliate_links / words_per_300) > 2:
            return -6  # Reduced penalty

        return 0

    def _check_pagination(self, url: str, soup: BeautifulSoup) -> int:
        """Check for pagination without proper stitching: -5"""
        # Check URL for page parameter
        if 'page=' in url or '/page/' in url:
            # Check if has rel=next (proper pagination)
            next_link = soup.find('link', rel='next')
            if not next_link:
                return -5
        return 0

    def _check_clickbait(self, title: str) -> int:
        """Check for clickbait patterns: -3 (reduced from -6)"""
        title_lower = title.lower()

        for pattern in self.clickbait_patterns:
            if re.search(pattern, title_lower):
                return -3  # Reduced penalty

        return 0

    def _check_domain_quality(self, url: str) -> int:
        """Check domain quality: +5 for trusted, -4 if suspicious"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Trusted domains (academic, research, major news)
        trusted_domains = [
            '.edu',  # Educational institutions
            'stanford.edu', 'mit.edu', 'harvard.edu', 'berkeley.edu',
            'reuters.com', 'bloomberg.com', 'bbc.com', 'theguardian.com',
            'nature.com', 'science.org', 'arxiv.org'
        ]

        for trusted in trusted_domains:
            if trusted in domain:
                return 5  # Bonus for trusted domains

        # Suspicious patterns (penalties)
        suspicious_patterns = [
            r'\d{4,}',  # Many numbers in domain
            r'cheap',
            r'deals',
            r'buy',
            r'discount',
            r'-ads',
            r'promo'
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, domain):
                return -4  # Penalty for suspicious

        return 0

    def score_pdf_content(self, url: str, pdf_metadata: Dict, extracted_content: Dict) -> Tuple[int, Dict]:
        """
        Score PDF content quality using 7 weighted signals (sum = 100 points)

        Signals:
        1. Metadata Completeness (max 15) - Title=5, Author=5, Subject=3, Keywords=2
        2. Date Recency (max 12)
        3. Domain Trust (max 20)
        4. Content Length (max 19)
        5. Document Structure (max 18)
        6. Words-per-Page (max 10)
        7. Named Entities (max 6)

        Returns: (score, details_dict)

        Args:
            url: PDF URL
            pdf_metadata: Dict with PDF metadata (title, author, creation_date, etc.)
            extracted_content: Dict with extracted content (text, word_count, etc.)
        """
        score = 0
        details = {}

        # ===== 1. Metadata Completeness (max 15) =====
        metadata_score = 0
        title = pdf_metadata.get('title', '')
        author = pdf_metadata.get('author', '')
        subject = pdf_metadata.get('subject', '')
        keywords = pdf_metadata.get('keywords', '')

        if len(title) >= 4:
            metadata_score += 5
        if len(author) >= 3:
            metadata_score += 5
        if subject:
            metadata_score += 3
        if keywords:
            metadata_score += 2

        score += metadata_score
        details['metadata_completeness'] = {'score': metadata_score, 'max': 15}

        # ===== 2. Date Recency (max 12) =====
        date_score = 0
        threshold_date = datetime.now() - timedelta(days=730)  # 2 years
        try:
            date_str = pdf_metadata.get('creation_date') or pdf_metadata.get('modification_date')
            if date_str:
                # Handle PDF date format (D:YYYYMMDDHHmmSS...)
                if date_str.startswith('D:'):
                    date_str = date_str[2:16]  # Extract YYYYMMDDHHmmSS
                    date_obj = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                else:
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

                if date_obj >= threshold_date:
                    date_score = 12
        except:
            pass

        score += date_score
        details['date_recency'] = {'score': date_score, 'max': 12}

        # ===== 3. Domain Trust (max 20) =====
        domain_score = self._check_pdf_domain_quality_v2(url)
        score += domain_score
        details['domain_trust'] = {'score': domain_score, 'max': 20}

        # ===== 4. Content Length (max 19) =====
        word_count = extracted_content.get('word_count', 0)

        if 600 <= word_count <= 10000:
            length_score = 19
        elif word_count > 10000:
            # All content above 10k words gets full points (comprehensive reports)
            length_score = 19
        elif 300 <= word_count <= 599:
            length_score = 8
        elif word_count < 300:
            length_score = 0
        else:
            length_score = 0

        score += length_score
        details['content_length'] = {'score': length_score, 'max': 19, 'word_count': word_count}

        # ===== 5. Document Structure (max 18) =====
        # Count headings from structure
        structure_data = extracted_content.get('structure', {})
        block_counts = structure_data.get('block_counts', {})

        heading_count = (
            block_counts.get('title', 0) +
            block_counts.get('h1', 0) +
            block_counts.get('h2', 0) +
            block_counts.get('h3', 0) +
            block_counts.get('h4', 0)
        )

        if heading_count >= 3:
            structure_score = 18
        elif heading_count >= 1:
            structure_score = 9
        else:
            structure_score = 0

        score += structure_score
        details['document_structure'] = {'score': structure_score, 'max': 18, 'heading_count': heading_count}

        # ===== 6. Words-per-Page Density (max 10) =====
        # Try multiple sources for page count
        pages_data = extracted_content.get('metadata', {}).get('pages', 0)
        pages = len(pages_data) if isinstance(pages_data, list) else (pages_data if isinstance(pages_data, int) else 0)

        # Fallback: try to get from pages list
        if pages == 0:
            pages_list = extracted_content.get('pages', [])
            if isinstance(pages_list, list):
                pages = len(pages_list)

        # Fallback: try to get from pdf_metadata
        if pages == 0:
            pages = pdf_metadata.get('num_pages', 0)

        if pages > 0 and word_count > 0:
            words_per_page = word_count / pages

            # Granular scoring with rounding tolerance
            # Give 6 points if within 10 of optimal range (190-210 or 490-510)
            if 210 <= words_per_page <= 490:
                wpp_score = 10  # Optimal range
            elif (190 <= words_per_page < 210) or (490 < words_per_page <= 510):
                wpp_score = 6   # Very close to optimal (e.g., 198.3)
            elif (100 <= words_per_page < 190) or (510 < words_per_page <= 800):
                wpp_score = 4   # Acceptable
            else:
                wpp_score = 0   # Too sparse or too dense
        else:
            words_per_page = 0
            wpp_score = 0

        score += wpp_score
        details['words_per_page'] = {'score': wpp_score, 'max': 10, 'wpp': round(words_per_page, 1)}

        # ===== 7. Named Entities in Opening (max 6) =====
        # Get opening content (up to 500 chars from first few pages/blocks)
        pages = extracted_content.get('pages', [])
        first_text = ''
        if pages and len(pages) > 0:
            accumulated_text = []
            # Look through first 5 pages to gather opening text
            for page_idx in range(min(5, len(pages))):
                blocks = pages[page_idx].get('blocks', [])
                for block in blocks:
                    block_type = block.get('type', '')
                    # Skip header/footer, but include title, headings, body, paragraph, subtext
                    if block_type not in ['header_footer']:
                        text = block.get('text', '')
                        if text:
                            accumulated_text.append(text)
                            # Stop when we have enough text
                            if len(' '.join(accumulated_text)) >= 500:
                                break
                if len(' '.join(accumulated_text)) >= 500:
                    break
            first_text = ' '.join(accumulated_text)[:500]

        # Count mid-sentence capitalized words (proper noun heuristic)
        proper_noun_count = 0
        if first_text:
            # Split into words, skip first word of sentences
            words = first_text.split()
            for i, word in enumerate(words):
                # Skip if it's the start of the text or follows punctuation
                if i > 0 and len(words[i-1]) > 0 and words[i-1][-1] not in '.!?':
                    # Check if word is capitalized (and not all caps, and not too short)
                    if word and len(word) > 1 and word[0].isupper() and not word.isupper():
                        proper_noun_count += 1

        entity_score = 6 if proper_noun_count >= 2 else 0
        score += entity_score
        details['named_entities'] = {'score': entity_score, 'max': 6, 'count': proper_noun_count}

        # Clamp score to 0-100 (should not exceed due to our design)
        score = max(0, min(100, score))

        return score, details

    def _check_pdf_domain_quality_v2(self, url: str) -> int:
        """
        Check PDF domain quality for new scoring system
        Returns: 20 (highly trusted), 15 (trusted), 8 (good), 0 (unknown)
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Highly trusted (+20): Government, military, international orgs
        highly_trusted = [
            '.gov', '.mil',
            'whitehouse.gov', 'un.org', 'worldbank.org', 'imf.org', 'nber.org'
        ]
        for trusted in highly_trusted:
            if trusted in domain:
                return 20

        # Trusted (+15): Academic, top research, major consulting
        trusted_domains = [
            '.edu',
            'arxiv.org', 'nature.com', 'science.org',
            'microsoft.com', 'mckinsey.com', 'stanford.edu', 'mit.edu'
        ]
        for trusted in trusted_domains:
            if trusted in domain:
                return 15

        # Good (+8): News, generic non-profits
        good_domains = [
            'reuters.com', 'bloomberg.com', 'bbc.com'
        ]
        for good in good_domains:
            if good in domain:
                return 8

        # Generic .org gets +8 (but not if already matched above)
        if '.org' in domain:
            return 8

        # Unknown domains get 0
        return 0

    def _check_pdf_domain_quality(self, url: str) -> int:
        """Check PDF domain quality: +15 for highly trusted, +10 for trusted, +5 for good"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Highly trusted domains (government, international orgs, top research)
        highly_trusted = [
            '.gov',  # Government
            '.mil',  # Military
            'whitehouse.gov', 'state.gov', 'justice.gov',
            'unctad.org', 'un.org', 'worldbank.org', 'imf.org',  # International orgs
            'nber.org',  # National Bureau of Economic Research
        ]

        for trusted in highly_trusted:
            if trusted in domain:
                return 15

        # Trusted domains (academic, major research, established companies)
        trusted_domains = [
            '.edu',  # Educational institutions
            'stanford.edu', 'mit.edu', 'harvard.edu', 'berkeley.edu',
            'nature.com', 'science.org', 'arxiv.org',
            'microsoft.com', 'google.com', 'apple.com',
            'jpmorganchase.com', 'goldmansachs.com', 'mckinsey.com',
        ]

        for trusted in trusted_domains:
            if trusted in domain:
                return 10

        # Good domains (news, research institutions)
        good_domains = [
            'reuters.com', 'bloomberg.com', 'bbc.com',
            '.org',  # Non-profits
        ]

        for good in good_domains:
            if good in domain:
                return 5

        return 0

    def _check_pdf_content_length(self, extracted_content: Dict) -> int:
        """Check PDF content length optimized for research/reports: 600-10,000 words optimal"""
        word_count = extracted_content.get('word_count', 0)

        if 600 <= word_count <= 10000:
            return 12  # Optimal range for research PDFs
        elif 10000 < word_count <= 30000:
            return 8  # Long reports still valuable
        elif 300 <= word_count < 600:
            return 4  # Short but acceptable
        elif word_count < 300 or word_count > 50000:
            return -10  # Too short or too long
        else:
            return 2  # Edge cases

    def _check_homepage_or_archive(self, url: str, soup: BeautifulSoup, extracted_content: Dict) -> int:
        """
        Check if URL is a homepage or archive/listing page: -20

        Signals:
        1. URL path is empty or just '/' (homepage)
        2. Multiple article elements without detailed article schema on main page
        3. Content is very short with multiple links (listing behavior)
        """
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')

        # Signal 1: Homepage URL (domain root)
        if not path or path == '':
            # Strong signal - likely homepage
            return -20

        # Signal 2: Check for multiple article elements (archive/listing page)
        articles = soup.find_all(['article'])

        # If we have 3+ article elements, likely a listing page
        if len(articles) >= 3:
            # Check if the main page itself has Article schema
            # (Individual articles in listing won't have schema at page level)
            scripts = soup.find_all('script', type='application/ld+json')
            has_article_schema = False

            for script in scripts:
                try:
                    if not script.string:
                        continue
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        schema_type = data.get('@type', '')
                        if 'Article' in schema_type or 'NewsArticle' in schema_type:
                            has_article_schema = True
                            break
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                schema_type = item.get('@type', '')
                                if 'Article' in schema_type or 'NewsArticle' in schema_type:
                                    has_article_schema = True
                                    break
                except:
                    continue

            # Multiple articles but no article schema = listing page
            if not has_article_schema:
                return -15

        # Signal 3: Very short content with many links (snippet listing)
        content = extracted_content.get('content', '')
        word_count = len(content.split())

        if word_count < 400:
            # Count links in content
            body = soup.find(['article', 'main', 'body']) or soup
            links = body.find_all('a', href=True)

            # If short content with many links, likely snippets
            if len(links) > 10:
                return -10

        return 0

    def _check_incomplete_snippets(self, content: str) -> int:
        """
        Check for incomplete snippet content: -15

        Detects content with many lines ending in ellipsis (...), which indicates
        truncated article summaries rather than full content.

        Example from fintechnews.africa:
        "Over the past years, fintech has emerged as a driving force in Africa's..."
        "Forbes Middle East has released its annual selection of the Middle East's..."
        """
        if not content:
            return 0

        # Split into lines and check for ellipsis patterns
        lines = content.split('\n')
        lines_with_ellipsis = 0
        non_empty_lines = 0

        for line in lines:
            line = line.strip()
            if len(line) > 20:  # Only count substantial lines
                non_empty_lines += 1
                # Check if line ends with ellipsis (unicode or ascii)
                if line.endswith('...') or line.endswith('…'):
                    lines_with_ellipsis += 1

        # If we have at least 3 lines and >30% end with ellipsis, it's snippets
        if non_empty_lines >= 3:
            ellipsis_ratio = lines_with_ellipsis / non_empty_lines

            if ellipsis_ratio > 0.3:  # More than 30% of lines are truncated
                return -15
            elif ellipsis_ratio > 0.15:  # 15-30% truncated (borderline)
                return -8

        return 0

    def classify_score(self, score: int) -> str:
        """Classify score into quality categories"""
        if score >= 70:
            return "legit"
        elif score >= 40:
            return "maybe"
        else:
            return "skip"

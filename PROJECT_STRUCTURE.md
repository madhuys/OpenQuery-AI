# Project Structure: serper-search-app

**Root Path**: `/mnt/c/Users/madhu/aiseRchapp/serper-search-app`

**Auto-generated** by `analyse_project.py` - Do not edit manually

---

## Directory Tree

```
serper-search-app/
├── components/
│   ├── __init__.py (4 lines) [100.0B]
│   ├── analysis_results_panel.py (292 lines) [12.9KB]
│   ├── api_client.py (98 lines) [3.2KB]
│   ├── content_analysis_panel.py (479 lines) [21.9KB]
│   ├── content_drawer.py (112 lines) [4.4KB]
│   ├── progress_panel.py (455 lines) [23.7KB]
│   ├── search_panel.py (206 lines) [9.9KB]
│   ├── search_panel_v2.py (668 lines) [38.1KB]
│   ├── semantic_results_tab.py (255 lines) [11.2KB]
│   ├── serper_results_v2.py (240 lines) [11.6KB]
│   ├── sidebar.py (82 lines) [3.4KB]
│   ├── source_viewer.py (113 lines) [5.1KB]
│   ├── tab_failed_pdfs.py (429 lines) [20.8KB]
│   ├── tab_scoring.py (312 lines) [13.2KB]
│   └── tab_search.py (39 lines) [1.9KB]
├── config/
│   ├── __init__.py (29 lines) [657.0B]
│   ├── settings.py (485 lines) [21.1KB]
│   └── user_settings.json (120 lines) [3.3KB]
├── db/
│   ├── cache_schema.sql (202 lines) [9.9KB]
│   ├── cache_schema_embeddings.sql (58 lines) [3.6KB]
│   ├── cache_schema_hybrid.sql (160 lines) [7.7KB]
│   ├── cache_schema_pdf.sql (70 lines) [3.1KB]
│   └── migration_pdf_fingerprints.sql (20 lines) [1.1KB]
├── docs/
│   ├── superpowers/
│   │   ├── plans/
│   │   │   └── 2026-06-29-openquery-ddg-integration.md (171 lines) [6.9KB]
│   │   └── specs/
│   │       └── 2026-06-29-openquery-ddg-design.md (44 lines) [3.5KB]
│   ├── AGENT_CONTEXT.md (36 lines) [1.8KB]
│   └── HOW_IT_WORKS.md (100 lines) [6.3KB]
├── downloaded_pdfs/
├── pages/
│   ├── 2_🗂️_History.py (654 lines) [28.6KB]
│   ├── 3_⚙️_Settings.py (889 lines) [38.6KB]
│   ├── 4_🔍_Live_Search.py (696 lines) [35.2KB]
│   ├── 5_🔍_Search_V2.py (396 lines) [19.6KB]
│   ├── 6_🔍_Search_V3.py (472 lines) [24.6KB]
│   └── home.py (44 lines) [1.6KB]
├── scripts/
│   ├── analyse_project.py (497 lines) [22.3KB]
│   ├── cleanup_project.py (272 lines) [11.6KB]
│   ├── clear_all_data.py (244 lines) [9.9KB]
│   └── reprocess_pdfs.py (62 lines) [2.7KB]
├── services/
│   ├── helpers/
│   │   ├── __init__.py (40 lines) [1.1KB]
│   │   ├── content_scorer.py (666 lines) [30.3KB]
│   │   ├── content_utils.py (59 lines) [2.1KB]
│   │   ├── date_provenance.py (261 lines) [10.9KB]
│   │   ├── freshness_checker.py (232 lines) [11.7KB]
│   │   ├── nlp_analyzer.py (305 lines) [13.5KB]
│   │   ├── pdf_processor.py (227 lines) [9.1KB]
│   │   ├── query_normalizer.py (149 lines) [5.5KB]
│   │   ├── text_post_processor.py (230 lines) [8.6KB]
│   │   └── url_utils.py (92 lines) [3.5KB]
│   ├── __init__.py (15 lines) [400.0B]
│   ├── background_queue_service.py (380 lines) [15.2KB]
│   ├── base_cache_service.py (476 lines) [21.3KB]
│   ├── base_provider.py (29 lines) [839.0B]
│   ├── cache_service.py (201 lines) [11.7KB]
│   ├── chunk_matcher_service.py (349 lines) [16.7KB]
│   ├── chunktext.json (7767 lines) [694.9KB]
│   ├── ddg_service.py (82 lines) [3.0KB]
│   ├── embedding_cache_service.py (226 lines) [8.6KB]
│   ├── embedding_service.py (245 lines) [9.8KB]
│   ├── html_cache_service.py (817 lines) [34.3KB]
│   ├── html_fast_lane_service.py (236 lines) [10.3KB]
│   ├── html_processing_service.py (394 lines) [16.5KB]
│   ├── json_font_classifier.py (607 lines) [27.2KB]
│   ├── pdf_cache_service.py (806 lines) [33.5KB]
│   ├── pdf_extractor_unified_complete.py (1319 lines) [57.0KB]
│   ├── pdf_fast_lane_service.py (396 lines) [16.9KB]
│   ├── pdf_processing_service.py (612 lines) [31.3KB]
│   ├── pdf_processor.py (72 lines) [3.0KB]
│   ├── pdf_service.py (485 lines) [21.1KB]
│   ├── router_service.py (440 lines) [20.4KB]
│   ├── search_factory.py (28 lines) [1.0KB]
│   ├── semantic_search_service.py (176 lines) [8.4KB]
│   └── serper_service.py (136 lines) [5.3KB]
├── tests/
│   ├── __init__.py (3 lines) [39.0B]
│   └── test_search_providers.py (21 lines) [971.0B]
├── app.py (19 lines) [566.0B]
├── background_worker.py (426 lines) [20.8KB]
├── main.py (1115 lines) [52.6KB]
├── PROJECT_STRUCTURE.md (499 lines) [24.8KB]
├── README.md (162 lines) [10.5KB]
├── requirements.txt (45 lines) [883.0B]
├── restart.sh (60 lines) [2.3KB]
└── start.bat [502.0B]
```

---

## Project Statistics

- **Total Files**: 81
- **Total Directories**: 13
- **Total Lines of Code**: 30,410

### Files by Extension

- `.py`: 65 files
- `.md`: 6 files
- `.sql`: 5 files
- `.json`: 2 files
- `.txt`: 1 file
- `.sh`: 1 file
- `.bat`: 1 file

---

## Codebase Map

### Functions

**2_🗂️_History.py**
- `get_cache_service()` → line 27
- `format_type_chip(content_type)` → line 357
- `format_freshness_chip(freshness)` → line 363

**4_🔍_Live_Search.py**
- `get_app_settings()` → line 25
- `get_search_service()` → line 30
- `render_search_page()` → line 35
- `fetch_page(page_num, query_text)` → line 348

**5_🔍_Search_V2.py**
- `build_payload(query, params, page)` → line 24
- `call_single_search(payload)` → line 75
- `call_search_v2_api(params)` → line 89
- `call_analyze_url_api(url, index)` → line 236
- `render_search_v2_page()` → line 264

**6_🔍_Search_V3.py**
- `build_payload(query, params, page)` → line 27
- `call_single_search(payload)` → line 78
- `call_search_v2_api(params)` → line 92
- `call_analyze_url_api(url, index)` → line 239
- `render_search_v2_page()` → line 267

**analyse_project.py**
- `main()` → line 558

**analysis_results_panel.py**
- `_convert_text_to_markdown_html(text)` → line 14
- `_load_full_pdf_content(url)` → line 99
- `_get_cache_indicator(result)` → line 142
- `render_analysis_results_panel(result, url)` → line 162
- `_render_success_analysis(result)` → line 195
- `toggle_content()` → line 273
- `_render_filtered_analysis(result)` → line 315
- `_render_error_analysis(result)` → line 338

**api_client.py**
- `check_api_status()` → line 16
- `get_gpu_status()` → line 29
- `search_query(payload)` → line 44
- `analyze_stream(payload, timeout)` → line 60
- `process_pdfs(pdf_results, enable_spacy, spacy_require_gpu, timeout)` → line 78
- `get_failed_pdfs()` → line 104
- `retry_pdf_download(url, timeout)` → line 113

**background_queue_service.py**
- `get_queue_service()` → line 455

**background_worker.py**
- `reset_stuck_items_in_queue(queue_service)` → line 74
- `process_protected_pdf_download(url, queue_id)` → line 107
- `main()` → line 516

**base_cache_service.py**
- `retry_on_db_lock(max_retries, delay)` → line 21
- `decorator(func)` → line 23
- `wrapper()` → line 25

**cleanup_project.py**
- `main()` → line 300

**clear_all_data.py**
- `clear_downloaded_pdfs()` → line 20
- `clear_outputs_directory()` → line 63
- `clear_database_cache()` → line 106
- `clear_background_queue()` → line 160
- `clear_processing_tracker()` → line 214
- `clear_embeddings_database()` → line 234
- `main()` → line 282

**content_analysis_panel.py**
- `_convert_text_to_markdown_html(text)` → line 13
- `_load_full_pdf_content(url)` → line 98
- `render_content_analysis_panel()` → line 141
- `_render_cache_match_info()` → line 173
- `_count_pdfs(results)` → line 200
- `_render_header(pdf_count, pdf_results)` → line 214
- `_render_summary_metrics(results)` → line 248
- `_display_successful_results(results)` → line 268
- `_display_filtered_results(results)` → line 286
- `_display_failed_results(results)` → line 302
- `_render_result_expander(result, idx, count, result_type)` → line 318
- `_get_cache_indicator(result)` → line 342
- `_render_success_content(result, idx)` → line 362
- `_render_filtered_content(result)` → line 467
- `_render_failed_content(result)` → line 482
- `_display_processing_summary(results)` → line 508
- `_display_pdf_processing_results()` → line 527
- `_render_pdf_result(pdf_result, idx)` → line 553

**content_drawer.py**
- `_convert_text_to_markdown_html(text)` → line 9
- `render_content_drawer(content, drawer_key, title)` → line 91

**content_utils.py**
- `compute_content_hash(html)` → line 10
- `normalize_text(text)` → line 54

**embedding_service.py**
- `get_embedding_stats()` → line 68
- `embed_document_sync(url, doc_type, chunks, doc_id)` → line 122
- `embed_document_async(url, doc_type, chunks, doc_id)` → line 269

**home.py**
- `get_cache_service()` → line 16
- `get_date_detector()` → line 21
- `get_app_settings()` → line 26
- `render_home()` → line 31

**html_fast_lane_service.py**
- `process_html_with_timeout(url, index, progress_callback, timeout, settings, fast_lane_mode)` → line 33
- `process_html_fast_lane(url, index, progress_callback, settings)` → line 83

**html_processing_service.py**
- `_extract_html_structure(html, title, cleaned_text)` → line 33
- `process_html_complete(url, index, progress_callback, settings, fast_lane_mode)` → line 95

**json_font_classifier.py**
- `classify_pdf_json(pdf_extraction, config)` → line 723

**main.py**
- `get_global_router()` → line 49
- `get_app_settings()` → line 61
- `root()` → line 185
- `unified_search(request)` → line 196
- `analyze_urls_stream(request)` → line 343
- `generate()` → line 359
- `progress_callback(index, stage, percent)` → line 381
- `live_search(request)` → line 534
- `execute_search(task_name, page_num, search_req)` → line 614
- `match_highlight(request)` → line 756
- `process_pdfs(request)` → line 857
- `kill_process_on_port(port)` → line 931
- `search_v2(request)` → line 991
- `analyze_url(request)` → line 1087
- `semantic_search(request)` → line 1187

**pdf_extractor_unified_complete.py**
- `validate_pdf_file(pdf_path)` → line 43
- `_process_single_page(doc, page_num)` → line 98
- `extract_pdf_with_fonts(pdf_path, max_pages)` → line 176
- `extract_metadata(doc, num_pages)` → line 296
- `calculate_font_statistics(font_sizes)` → line 330
- `get_default_font_stats()` → line 416
- `is_artifact(text)` → line 445
- `clean_all_blocks_batch(blocks, enable_spell_check)` → line 455
- `classify_text_by_font_size(font_size, thresholds, text)` → line 530
- `extract_structured_blocks_from_spans(page, font_thresholds)` → line 562
- `detect_headers_footers(structured_pages)` → line 681
- `create_chunks_from_blocks(structured_pages)` → line 771
- `split_chunk_if_needed(chunk, base_chunk_id)` → line 879
- `generate_fingerprint(metadata, file_size_mb)` → line 997
- `create_sections_from_flat_blocks(content_blocks)` → line 1023
- `chunk_section_blocks(section, max_chars)` → line 1080
- `merge_small_chunks(chunks, min_chars)` → line 1142
- `restructure_content_to_sections(content_blocks)` → line 1249
- `extract_pdf_complete(pdf_path, max_pages, enable_spell_check)` → line 1282
- `_extract_blocks_for_page(page_data, thresholds)` → line 1319
- `check_if_scanned_pdf(pdf_path, check_pages)` → line 1473

**pdf_fast_lane_service.py**
- `time_limit(seconds)` → line 36
- `signal_handler(signum, frame)` → line 41
- `process_pdf_with_timeout(url, index, progress_callback, timeout)` → line 57
- `process_pdf_fast_lane(url, index, progress_callback, settings)` → line 106
- `batch_process_pdfs_fast_lane(pdf_urls, progress_callback, settings, max_workers)` → line 399

**pdf_processing_service.py**
- `process_pdf_complete(url, index, progress_callback, max_size_mb, enable_scoring, timeout, max_retries)` → line 37

**pdf_processor.py**
- `extract_pdf_title(pdf_path)` → line 23
- `extract_pdf_date(pdf_path)` → line 55
- `extract_pdf_text(pdf_path, max_chars)` → line 116
- `process_pdf(pdf_path, max_text_chars)` → line 166
- `validate_pdf(pdf_path)` → line 242

**pdf_service.py**
- `_get_browser_headers(url)` → line 57
- `_download_with_curl_cffi(url, filepath, index, progress_callback)` → line 76
- `_download_with_requests(url, filepath, index, progress_callback)` → line 180
- `_download_with_session(url, filepath, index, progress_callback)` → line 234
- `_download_with_httpx(url, filepath, index, progress_callback)` → line 290
- `_download_with_playwright(url, filepath, index, progress_callback)` → line 330
- `download_pdf_parallel(url, index, progress_callback, max_retries, timeout, max_size_mb)` → line 407

**progress_panel.py**
- `render_progress_panel(cache, app_settings, search_clicked, search_params)` → line 14
- `_handle_pdf_processing(app_settings, settings_dict)` → line 36
- `_execute_search_and_analysis(cache, search_params, app_settings, settings_dict)` → line 71
- `_perform_search(base_payload, pages_needed, disable_cache, cache, app_settings, start_time, query_id, parallel_workers, timeout_setting, num_results, document_search, settings_dict)` → line 133
- `_handle_full_cache_hit(page_results, start_time)` → line 249
- `_extract_urls_from_results(page_results, page_num)` → line 292
- `_handle_search_results(all_results, urls, start_time, total_serper_time, cache_hit, query_id, parallel_workers, timeout_setting, app_settings, all_cache_batches, cache, settings_dict)` → line 316
- `_start_streaming_analysis(urls, search_elapsed, total_serper_time, cache_hit, query_id, parallel_workers, timeout_setting, app_settings, all_cache_batches, cache, start_time, settings_dict)` → line 344
- `_update_progress_bar(progress_bar, stage, percent)` → line 491
- `_update_result_progress(url_progress_bars, url_status_text, idx, result, status)` → line 504
- `_handle_analysis_complete(data, all_results, analyze_start, start_time, total_serper_time, status_placeholder, progress_placeholder, progress_container, all_cache_batches, cache, query_id, urls)` → line 518
- `_display_raw_json()` → line 553

**query_normalizer.py**
- `normalize_query(query)` → line 11
- `find_similar_queries(query, cached_queries, threshold, limit)` → line 79
- `find_best_cache_match(query, cached_queries, threshold)` → line 115
- `get_similarity_score(query1, query2)` → line 142
- `analyze_query_variants(query)` → line 164

**reprocess_pdfs.py**
- `clear_pdf_data()` → line 9

**router_service.py**
- `_get_html_executor(max_workers)` → line 27
- `_get_pdf_executor(max_workers)` → line 38
- `_cleanup_executors()` → line 46
- `route_urls_async(urls, max_workers, progress_callback)` → line 488

**search_factory.py**
- `get_search_provider(provider_name)` → line 10
- `search_and_extract(query, search_type, provider)` → line 20

**search_panel.py**
- `render_search_panel(app_settings)` → line 11

**search_panel_v2.py**
- `render_search_panel_v2()` → line 10

**semantic_results_tab.py**
- `render_semantic_results_tab(query, analyzed_urls, api_base_url)` → line 14
- `render_semantic_match_card(match, index)` → line 170
- `get_embedding_stats(api_base_url)` → line 282

**serper_results_v2.py**
- `render_result_card(result, index, allow_expander, group_id)` → line 9
- `on_click()` → line 97
- `render_serper_results_v2(serper_response, query_info, results_by_query)` → line 176

**serper_service.py**
- `search_and_extract(query, search_type)` → line 144

**sidebar.py**
- `render_sidebar()` → line 10
- `_render_about_section()` → line 23
- `_render_api_status()` → line 42
- `_render_system_resources()` → line 67

**source_viewer.py**
- `render_source_viewer(match_result)` → line 9

**tab_failed_pdfs.py**
- `render_failed_pdfs_tab()` → line 18
- `_fetch_queue_data()` → line 58
- `_display_queue_stats()` → line 77
- `_display_active_items()` → line 98
- `_display_completed_items()` → line 124
- `_display_failed_items()` → line 139
- `_display_failed_item_with_upload(item, idx)` → line 156
- `_display_queue_item(item, status_emoji, status_text, show_duration, show_error)` → line 228
- `_format_timestamp(timestamp_str)` → line 270
- `_calculate_duration(start_str, end_str)` → line 299
- `_process_manual_upload(uploaded_file, url, queue_id, item)` → line 322

**tab_scoring.py**
- `render_scoring_tab(app_settings)` → line 11
- `_render_scoring_settings(scoring_settings)` → line 40
- `_render_left_column_settings(scoring_settings)` → line 85
- `_render_content_length_settings(scoring_settings)` → line 151
- `_render_right_column_settings(scoring_settings)` → line 219
- `_render_wpp_settings(scoring_settings)` → line 272
- `_render_save_controls(app_settings, settings_values)` → line 319
- `_save_settings(app_settings, settings_values)` → line 331
- `_render_export_import_controls(app_settings)` → line 363

**tab_search.py**
- `render_search_tab(cache, app_settings)` → line 13

**test_search_providers.py**
- `test_search_factory_default()` → line 9
- `test_search_factory_ddg()` → line 15
- `test_ddg_search_execution()` → line 21

**text_post_processor.py**
- `clean_wikipedia_tables(text)` → line 16
- `remove_orphaned_hyphens(text)` → line 66
- `normalize_line_breaks(text, source)` → line 103
- `remove_wiki_edit_markers(text)` → line 127
- `remove_excessive_whitespace(text)` → line 149
- `clean_extracted_text(text, source, options)` → line 174
- `clean_for_display(text, source, max_length)` → line 237
- `clean_for_embedding(text, source)` → line 257
- `debug_cleaning_pipeline(text, source)` → line 284

**url_utils.py**
- `normalize_url(url, tracking_params)` → line 18
- `extract_domain(url)` → line 89
- `compute_content_hash(content)` → line 107

### Classes

**analyse_project.py**
- `CodebaseMapper` → line 24 (methods: __init__, visit_Import, visit_ImportFrom, visit_FunctionDef, visit_AsyncFunctionDef, ... (+3 more))
- `ProjectAnalyzer` → line 153 (methods: __init__, should_ignore, count_lines, analyze_file, analyze_python_file, ... (+6 more))

**background_queue_service.py**
- `BackgroundQueueService` → line 19 (methods: __init__, _init_database, _get_connection, add_to_queue, get_next_pending, ... (+9 more))

**background_worker.py**
- `BackgroundWorker` → line 268 (methods: __init__, _signal_handler, start, stop, cleanup_old_completed)

**base_cache_service.py**
- `BaseCacheService` → line 39 (methods: __init__, _init_database, dict_factory, close, upsert_domain, ... (+13 more))

**base_provider.py**
- `BaseSearchProvider` → line 8 (methods: search, extract_urls)

**cache_service.py**
- `CacheService` → line 11 (methods: __init__, close, get_search_history, get_url_info, purge_url, ... (+35 more))

**chunk_matcher_service.py**
- `ChunkMatcherService` → line 12 (methods: __init__, normalize_text, load_document, _load_pdf_from_json, find_chunk_in_document, ... (+1 more))

**cleanup_project.py**
- `ImportAnalyzer` → line 29 (methods: __init__, visit_Import, visit_ImportFrom)
- `ProjectCleanup` → line 63 (methods: __init__, find_python_files, extract_imports, build_import_graph, find_unused_files, ... (+3 more))

**content_scorer.py**
- `ContentScorer` → line 14 (methods: __init__, score_content, _check_schema_org, _check_byline, _check_publication_date, ... (+17 more))

**date_provenance.py**
- `DateProvenanceDetector` → line 15 (methods: __init__, detect_dates, _extract_jsonld_dates, _extract_og_dates, _extract_byline_dates, ... (+2 more))

**ddg_service.py**
- `DuckDuckGoProvider` → line 12 (methods: search, extract_urls)

**embedding_cache_service.py**
- `EmbeddingCacheService` → line 12 (methods: __init__, _get_connection, _ensure_tables, check_embedding_status, record_embedding_start, ... (+7 more))

**embedding_service.py**
- `AzureOpenAIEmbeddingService` → line 14 (methods: __init__, embed_batch)

**freshness_checker.py**
- `FreshnessChecker` → line 17 (methods: __init__, check_freshness, _check_http_validators, extract_feed_updated_date, extract_sitemap_lastmod, ... (+1 more))

**html_cache_service.py**
- `HTMLCacheService` → line 17 (methods: record_fetch, record_processed_simple, _get_latest_raw_id, record_processed, record_html_processing_error, ... (+10 more))

**html_fast_lane_service.py**
- `TimeoutException` → line 28 (methods: no methods)

**json_font_classifier.py**
- `FontClassifier` → line 19 (methods: __init__, process_document, _estimate_page_height, _mark_header_footer_blocks, _compute_top_10_fonts, ... (+10 more))

**main.py**
- `SearchRequest` → line 67 (methods: no methods)
- `AnalyzeRequest` → line 86 (methods: no methods)
- `ProcessPDFsRequest` → line 102 (methods: no methods)
- `AnalyzeURLRequest` → line 111 (methods: no methods)
- `SemanticSearchRequest` → line 117 (methods: no methods)
- `LiveSearchRequest` → line 125 (methods: no methods)
- `LiveSearchResult` → line 147 (methods: no methods)
- `LiveSearchResponse` → line 161 (methods: no methods)
- `MatchHighlightRequest` → line 167 (methods: no methods)
- `MatchHighlightResponse` → line 174 (methods: no methods)

**nlp_analyzer.py**
- `NLPAnalyzer` → line 20 (methods: __init__, analyze_content, _extract_structured_data, _analyze_domain, _analyze_text_quality, ... (+6 more))

**pdf_cache_service.py**
- `PDFCacheService` → line 16 (methods: should_download_pdf, record_pdf_download_success, record_pdf_download_failure, record_pdf_processing_success, record_pdf_processing_failure, ... (+13 more))

**pdf_extractor_unified_complete.py**
- `PDFExtractor` → line 1503 (methods: __init__, extract, extract_metadata_only)

**pdf_fast_lane_service.py**
- `TimeoutException` → line 30 (methods: no methods)

**pdf_processor.py**
- `PDFDeduplicator` → line 15 (methods: __init__, is_duplicate, _generate_fingerprint, record_processed)

**router_service.py**
- `ContentRouter` → line 60 (methods: __init__, check_cache, classify_url, route_urls, process_pdfs, ... (+1 more))

**semantic_search_service.py**
- `SemanticSearchService` → line 12 (methods: __init__, _preload_embeddings, cosine_similarity, search, get_statistics)

**serper_service.py**
- `SerperClient` → line 19 (methods: __init__, search, extract_urls)

**settings.py**
- `SearchSettings` → line 13 (methods: no methods)
- `GeographicSettings` → line 21 (methods: no methods)
- `ResultSettings` → line 34 (methods: total_results)
- `TimeFilterSettings` → line 61 (methods: get_tbs_value)
- `AnalysisSettings` → line 97 (methods: no methods)
- `CacheSettings` → line 135 (methods: serper_freshness_by_type, html_staleness_by_type)
- `PDFSettings` → line 196 (methods: __post_init__)
- `PDFScoringSettings` → line 217 (methods: no methods)
- `BackgroundProcessingSettings` → line 273 (methods: no methods)
- `EmbeddingSettings` → line 304 (methods: no methods)
- `AppSettings` → line 329 (methods: to_dict, to_json, from_dict, from_json, save, ... (+1 more))

### Constants

- `API_BASE_URL` → api_client.py:10, semantic_results_tab.py:11, 5_🔍_Search_V2.py:21, 6_🔍_Search_V3.py:24
- `CHARS_FROM_END` → pdf_processor.py:20
- `CHARS_FROM_MIDDLE` → pdf_processor.py:19
- `CHARS_FROM_START` → pdf_processor.py:18
- `CHUNK_SIZE` → pdf_service.py:50
- `CONNECT_TIMEOUT` → pdf_service.py:47
- `DEFAULT_SETTINGS` → settings.py:571
- `DEFAULT_TRACKING_PARAMS` → url_utils.py:12
- `EXAMPLE_LOCATIONS` → settings.py:548
- `FIRST_BYTE_TIMEOUT` → pdf_service.py:48
- `HAS_CURL_CFFI` → pdf_service.py:26, pdf_service.py:28
- `HAS_PLAYWRIGHT` → pdf_service.py:33, pdf_service.py:35
- `HAS_PLAYWRIGHT_SUPPORT` → background_worker.py:57, background_worker.py:59
- `HAS_PYMUPDF` → pdf_extractor_unified_complete.py:24, pdf_extractor_unified_complete.py:26
- `HAS_SPELLCHECKER` → pdf_extractor_unified_complete.py:31, pdf_extractor_unified_complete.py:35
- `MIN_SPEED_BPS` → pdf_service.py:51
- `PDF_DOWNLOAD_DIR` → pdf_service.py:43
- `READ_TIMEOUT` → pdf_service.py:49
- `SERPER_API_KEY` → serper_service.py:15
- `SERPER_BASE_URL` → serper_service.py:16
- `SETTINGS_FILE` → settings.py:575
- `SUPPORTED_COUNTRIES` → settings.py:449
- `SUPPORTED_LANGUAGES` → settings.py:506

---

## Variable Analysis

### Statistics

- **Unique Parameters**: 298
- **Unique Local Variables**: 1074
- **Unique Class Attributes**: 201
- **Unique Imports**: 161

### Most Common Parameters

- `url` (used 84 times)
- `text` (used 21 times)
- `index` (used 17 times)
- `progress_callback` (used 16 times)
- `query` (used 13 times)
- `url_id` (used 13 times)
- `result` (used 12 times)
- `app_settings` (used 12 times)
- `query_id` (used 12 times)
- `results` (used 11 times)
- `pdf_path` (used 11 times)
- `settings` (used 11 times)
- `title` (used 10 times)
- `filepath` (used 9 times)
- `node` (used 9 times)

### Naming Patterns

- **snake_case**: 1021 variables
- **camelCase/PascalCase**: 2 variables
- **Single character**: 5 variables

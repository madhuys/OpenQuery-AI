"""
Clear All Data Script

Clears:
1. All files in downloaded_pdfs/ directory (PDFs and subdirectories)
2. All JSON files in outputs/ directory (pdf_json and html_json)
3. Database cache tables (db/serper_cache.db)
4. Background queue database (db/background_queue.db)
5. Processing tracker log (logs/pdf_processing_tracker.json)

USE WITH CAUTION - This will delete all downloaded PDFs and cached data!
"""

import os
import shutil
from pathlib import Path
import sqlite3


def clear_downloaded_pdfs():
    """Remove all files and subdirectories in downloaded_pdfs/"""
    pdf_dir = Path("downloaded_pdfs")

    if not pdf_dir.exists():
        print(f"[INFO] {pdf_dir} does not exist, skipping...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING DOWNLOADED_PDFS DIRECTORY")
    print(f"{'='*80}\n")

    # Count files first
    files_to_delete = []
    dirs_to_delete = []

    for item in pdf_dir.iterdir():
        if item.is_file():
            files_to_delete.append(item)
        elif item.is_dir():
            dirs_to_delete.append(item)

    print(f"Found {len(files_to_delete)} files and {len(dirs_to_delete)} directories to delete\n")

    # Delete files
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            print(f"[DELETED] {file_path.name}")
        except Exception as e:
            print(f"[ERROR] Could not delete {file_path.name}: {e}")

    # Delete directories
    for dir_path in dirs_to_delete:
        try:
            shutil.rmtree(dir_path)
            print(f"[DELETED] {dir_path.name}/ (directory)")
        except Exception as e:
            print(f"[ERROR] Could not delete {dir_path.name}/: {e}")

    print(f"\n✓ Downloaded PDFs cleared: {len(files_to_delete)} files, {len(dirs_to_delete)} directories")


def clear_outputs_directory():
    """Remove all JSON files in outputs/ directory"""
    outputs_dir = Path("outputs")

    if not outputs_dir.exists():
        print(f"\n[INFO] {outputs_dir} does not exist, skipping...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING OUTPUTS DIRECTORY")
    print(f"{'='*80}\n")

    # Count files first
    files_to_delete = []
    dirs_to_delete = []

    for item in outputs_dir.iterdir():
        if item.is_file():
            files_to_delete.append(item)
        elif item.is_dir():
            dirs_to_delete.append(item)

    print(f"Found {len(files_to_delete)} files and {len(dirs_to_delete)} directories to delete\n")

    # Delete files
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            print(f"[DELETED] {file_path.name}")
        except Exception as e:
            print(f"[ERROR] Could not delete {file_path.name}: {e}")

    # Delete directories (pdf_json, html_json, etc.)
    for dir_path in dirs_to_delete:
        try:
            shutil.rmtree(dir_path)
            print(f"[DELETED] {dir_path.name}/ (directory)")
        except Exception as e:
            print(f"[ERROR] Could not delete {dir_path.name}/: {e}")

    print(f"\n✓ Outputs cleared: {len(files_to_delete)} files, {len(dirs_to_delete)} directories")


def clear_database_cache():
    """Clear all cache tables in the database"""
    cache_db = Path("db/serper_cache.db")

    if not cache_db.exists():
        print(f"\n[INFO] Cache database not found at {cache_db}, skipping...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING CACHE DATABASE")
    print(f"{'='*80}\n")

    try:
        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        if not tables:
            print("[INFO] No tables found in cache database")
            conn.close()
            return

        print(f"Found {len(tables)} tables\n")

        # Clear each table
        for (table_name,) in tables:
            try:
                # Get count before deletion
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                # Delete all rows
                cursor.execute(f"DELETE FROM {table_name}")
                conn.commit()

                print(f"[CLEARED] {table_name}: {count} rows deleted")
            except Exception as e:
                print(f"[ERROR] Could not clear table {table_name}: {e}")

        # Vacuum to reclaim space
        print("\n[VACUUM] Reclaiming database space...")
        cursor.execute("VACUUM")
        conn.commit()

        conn.close()
        print("\n✓ Cache database cleared and optimized")

    except Exception as e:
        print(f"[ERROR] Database error: {e}")


def clear_background_queue():
    """Clear background queue database"""
    queue_db = Path("db/background_queue.db")

    if not queue_db.exists():
        print(f"\n[INFO] Background queue database not found at {queue_db}, skipping...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING BACKGROUND QUEUE DATABASE")
    print(f"{'='*80}\n")

    try:
        conn = sqlite3.connect(str(queue_db))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        if not tables:
            print("[INFO] No tables found in queue database")
            conn.close()
            return

        print(f"Found {len(tables)} tables\n")

        # Clear each table
        for (table_name,) in tables:
            try:
                # Get count before deletion
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                # Delete all rows
                cursor.execute(f"DELETE FROM {table_name}")
                conn.commit()

                print(f"[CLEARED] {table_name}: {count} rows deleted")
            except Exception as e:
                print(f"[ERROR] Could not clear table {table_name}: {e}")

        # Vacuum to reclaim space
        print("\n[VACUUM] Reclaiming database space...")
        cursor.execute("VACUUM")
        conn.commit()

        conn.close()
        print("\n✓ Background queue database cleared and optimized")

    except Exception as e:
        print(f"[ERROR] Database error: {e}")


def clear_processing_tracker():
    """Clear processing tracker log"""
    tracker_log = Path("logs/pdf_processing_tracker.json")

    if not tracker_log.exists():
        print(f"\n[INFO] Processing tracker log not found at {tracker_log}, skipping...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING PROCESSING TRACKER LOG")
    print(f"{'='*80}\n")

    try:
        tracker_log.unlink()
        print(f"[DELETED] {tracker_log}")
        print("\n✓ Processing tracker log cleared")
    except Exception as e:
        print(f"[ERROR] Could not delete tracker log: {e}")


def clear_embeddings_database():
    """Clear embedding-related tables in the database"""
    cache_db = Path("db/serper_cache.db")

    if not cache_db.exists():
        print(f"\n[INFO] Cache database not found at {cache_db}, skipping embeddings...")
        return

    print(f"\n{'='*80}")
    print(f"CLEARING EMBEDDINGS DATABASE")
    print(f"{'='*80}\n")

    try:
        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Clear document_embeddings table
        try:
            cursor.execute("SELECT COUNT(*) FROM document_embeddings")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM document_embeddings")
            conn.commit()
            print(f"[CLEARED] document_embeddings: {count} rows deleted")
        except Exception as e:
            print(f"[INFO] document_embeddings table not found or error: {e}")

        # Clear embedding_status table
        try:
            cursor.execute("SELECT COUNT(*) FROM embedding_status")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM embedding_status")
            conn.commit()
            print(f"[CLEARED] embedding_status: {count} rows deleted")
        except Exception as e:
            print(f"[INFO] embedding_status table not found or error: {e}")

        # Vacuum to reclaim space
        print("\n[VACUUM] Reclaiming database space...")
        cursor.execute("VACUUM")
        conn.commit()

        conn.close()
        print("\n✓ Embeddings database cleared and optimized")

    except Exception as e:
        print(f"[ERROR] Database error: {e}")


def main():
    """Main function"""
    print("\n" + "="*80)
    print("CLEAR ALL DATA - PDFs, Databases, and Logs")
    print("="*80)
    print("\nThis will DELETE:")
    print("  1. All files in downloaded_pdfs/")
    print("  2. All subdirectories in downloaded_pdfs/")
    print("  3. All JSON files in outputs/ directory (pdf_json and html_json)")
    print("  4. All cache database entries (db/serper_cache.db)")
    print("  5. All background queue entries (db/background_queue.db)")
    print("  6. All embeddings (document_embeddings and embedding_status tables)")
    print("  7. Processing tracker log (logs/pdf_processing_tracker.json)")
    print("\n" + "="*80)

    # Ask for confirmation
    response = input("\nAre you sure you want to continue? Type 'yes' to confirm: ")

    if response.lower() != 'yes':
        print("\n[CANCELLED] Operation cancelled by user")
        return

    # Clear everything
    clear_downloaded_pdfs()
    clear_outputs_directory()
    clear_database_cache()
    clear_embeddings_database()
    clear_background_queue()
    clear_processing_tracker()

    print("\n" + "="*80)
    print("✓ ALL DATA CLEARED SUCCESSFULLY")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()

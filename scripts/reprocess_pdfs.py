"""
Script to clear PDF cache and embeddings to force reprocessing with new chunk merging logic
"""
import sqlite3
import shutil
from pathlib import Path


def clear_pdf_data():
    """Clear all PDF-related data to force reprocessing"""

    # 1. Clear PDF JSON files
    pdf_json_dir = Path('outputs/pdf_json')
    if pdf_json_dir.exists():
        print(f"📁 Clearing PDF JSON files from {pdf_json_dir}")
        for json_file in pdf_json_dir.glob('*.json'):
            json_file.unlink()
            print(f"   Deleted: {json_file.name}")

    # 2. Clear PDF embeddings from database
    db_path = 'db/serper_cache.db'
    if Path(db_path).exists():
        print(f"\n🗄️  Clearing PDF embeddings from {db_path}")
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        # Count before deletion
        cursor.execute("SELECT COUNT(*) FROM document_embeddings WHERE doc_type = 'pdf'")
        count_before = cursor.fetchone()[0]
        print(f"   PDF embeddings before: {count_before}")

        # Delete PDF embeddings
        cursor.execute("DELETE FROM document_embeddings WHERE doc_type = 'pdf'")
        conn.commit()

        # Count after deletion
        cursor.execute("SELECT COUNT(*) FROM document_embeddings WHERE doc_type = 'pdf'")
        count_after = cursor.fetchone()[0]
        print(f"   PDF embeddings after: {count_after}")
        print(f"   Deleted: {count_before - count_after} PDF embeddings")

        # Also clear embedding_status for PDFs
        cursor.execute("DELETE FROM embedding_status WHERE doc_type = 'pdf'")
        conn.commit()

        conn.close()

    # 3. Clear downloaded PDFs (optional - will be re-downloaded)
    downloads_dir = Path('downloads')
    if downloads_dir.exists():
        print(f"\n📥 Clearing downloaded PDFs from {downloads_dir}")
        pdf_count = 0
        for pdf_file in downloads_dir.glob('*.pdf'):
            pdf_file.unlink()
            pdf_count += 1
        print(f"   Deleted: {pdf_count} PDF files")

    print("\n✅ PDF data cleared successfully!")
    print("   Next search will reprocess all PDFs with new chunk merging logic (min 500 chars)")


if __name__ == '__main__':
    import sys

    # Confirm before deleting
    print("⚠️  This will delete all PDF cache data and force reprocessing.")
    print("   - PDF JSON files (outputs/pdf_json/*.json)")
    print("   - PDF embeddings (document_embeddings table)")
    print("   - Downloaded PDF files (downloads/*.pdf)")
    print()

    response = input("Continue? (yes/no): ").strip().lower()

    if response == 'yes':
        clear_pdf_data()
    else:
        print("❌ Cancelled")
        sys.exit(1)

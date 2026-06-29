#!/usr/bin/env python3
"""
Project Cleanup Script

Analyzes the project to find:
1. Unused Python files (not imported anywhere)
2. Test scripts (files starting with test_)
3. Old/deprecated files

Then organizes them:
- Unused files → renamed to .old → moved to old/ folder
- Test scripts → moved to test_scripts/ folder

Exceptions (never moved):
- cleanup_project.py (this file)
- analyse_project.py (analysis tool)
- app.py (main Streamlit app)
- main.py (main FastAPI server)
"""

import os
import re
import shutil
import ast
from pathlib import Path
from typing import Set, List, Dict


class ImportAnalyzer(ast.NodeVisitor):
    """AST visitor to extract import statements"""

    def __init__(self):
        self.imports = set()

    def visit_Import(self, node):
        """Visit import statements: import foo"""
        for alias in node.names:
            # Store both full path and all components
            full_name = alias.name
            self.imports.add(full_name)
            # Add each part of the path
            parts = full_name.split('.')
            for i in range(len(parts)):
                self.imports.add('.'.join(parts[:i+1]))

    def visit_ImportFrom(self, node):
        """Visit from imports: from foo import bar"""
        if node.module:
            # Store both full path and all components
            full_name = node.module
            self.imports.add(full_name)
            # Add each part of the path
            parts = full_name.split('.')
            for i in range(len(parts)):
                self.imports.add('.'.join(parts[:i+1]))

        # Also add imported names
        for alias in node.names:
            if alias.name != '*':
                self.imports.add(alias.name)


class ProjectCleanup:
    """Analyzes and cleans up project files"""

    # Files that should NEVER be moved or marked as old
    PROTECTED_FILES = {
        'cleanup_project.py',      # This script
        'analyse_project.py',      # Comprehensive analysis tool
        'app.py',                  # Main Streamlit app
        'main.py',                 # Main FastAPI server
        'README.md',               # Main documentation
        'HOW_IT_WORKS.md',         # Architecture documentation
        'PROJECT_STRUCTURE.md',    # Auto-generated structure
        'AGENT_CONTEXT.md',        # AI agent quick reference
        'PATTERNS.md',             # Code conventions
    }

    # Known old files (manually marked)
    KNOWN_OLD_FILES = {
        'pdf_extractor_old.py',
        'pdf_extractor_split.py',
        'pdf_downloader_threaded.py',
        'profile_pipeline.py',
        'analyze_files.py',       # Duplicate of analyse_project
        'analyze_variables.py',   # Merged into analyse_project.py
    }

    def __init__(self, root_path: str = "."):
        """Initialize cleanup analyzer"""
        self.root_path = Path(root_path).resolve()
        self.python_files: Set[Path] = set()
        self.imports_map: Dict[Path, Set[str]] = {}
        self.module_map: Dict[str, Path] = {}

    def find_python_files(self) -> List[Path]:
        """Find all Python files in project (excluding ignored directories)"""
        ignore_dirs = {
            '.git', '__pycache__', 'venv', 'env', '.venv',
            'old', 'test_scripts', '.next', 'node_modules',
            'logs', 'db'
        }

        python_files = []
        for py_file in self.root_path.rglob('*.py'):
            # Skip if in ignored directory
            if any(ignored in py_file.parts for ignored in ignore_dirs):
                continue

            # Skip helpers subdirectory files that are duplicates
            if 'helpers' in py_file.parts and 'optimised' in py_file.name.lower():
                continue

            python_files.append(py_file)

        return python_files

    def extract_imports(self, file_path: Path) -> Set[str]:
        """Extract all imports from a Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            analyzer = ImportAnalyzer()
            analyzer.visit(tree)
            return analyzer.imports

        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"  [WARNING] Could not parse {file_path.name}: {e}")
            return set()

    def build_import_graph(self):
        """Build a graph of all imports in the project"""
        print("[ANALYSIS] Analyzing imports...")

        # Find all Python files
        self.python_files = set(self.find_python_files())

        # Build module name → file path mapping
        for py_file in self.python_files:
            module_name = py_file.stem  # filename without .py
            self.module_map[module_name] = py_file

        # Extract imports from each file
        for py_file in self.python_files:
            imports = self.extract_imports(py_file)
            self.imports_map[py_file] = imports

    def find_unused_files(self) -> Set[Path]:
        """Find Python files that are never imported"""
        used_modules = set()

        # Collect all imported modules
        for imports in self.imports_map.values():
            used_modules.update(imports)

        # Find files that are never imported
        unused_files = set()

        for module_name, file_path in self.module_map.items():
            # Skip protected files
            if file_path.name in self.PROTECTED_FILES:
                continue

            # Skip __init__.py files (they're package markers)
            if file_path.name == '__init__.py':
                continue

            # Check if module is imported anywhere
            # Need to check both bare name (e.g., "cache_service") and full paths (e.g., "services.cache_service")
            is_used = False

            # Check exact match
            if module_name in used_modules:
                is_used = True
            else:
                # Check if any import path ends with this module name
                for used_module in used_modules:
                    if '.' in used_module and used_module.endswith('.' + module_name):
                        is_used = True
                        break

            if not is_used:
                # Also check if it's a main entry point (has if __name__ == '__main__')
                if not self.is_entry_point(file_path):
                    unused_files.add(file_path)

        return unused_files

    def is_entry_point(self, file_path: Path) -> bool:
        """Check if file is an entry point (has if __name__ == '__main__' or is in pages/)"""
        # Files in pages/ directory are Streamlit entry points
        if 'pages' in file_path.parts or file_path.parent.name == 'pages':
            return True

        # Check for main entry point
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                return 'if __name__' in content and '__main__' in content
        except:
            return False

    def find_test_scripts(self) -> List[Path]:
        """Find test scripts (files starting with test_)"""
        test_scripts = []

        for py_file in self.python_files:
            # Skip if already in test_scripts directory
            if 'test_scripts' in py_file.parts:
                continue

            # Check if filename starts with test_
            if py_file.name.startswith('test_'):
                test_scripts.append(py_file)

        return test_scripts

    def cleanup(self, dry_run: bool = False):
        """
        Perform cleanup operations

        Args:
            dry_run: If True, only print what would be done without actually doing it
        """
        print(f"\n[CLEANUP] Starting cleanup{' (DRY RUN)' if dry_run else ''}...\n")

        # Build import graph
        self.build_import_graph()

        # Create directories
        old_dir = self.root_path / 'old'
        test_dir = self.root_path / 'test_scripts'

        if not dry_run:
            old_dir.mkdir(exist_ok=True)
            test_dir.mkdir(exist_ok=True)

        # Step 1: Find and move unused files
        print("[UNUSED] Finding unused files...\n")
        unused_files = self.find_unused_files()

        # Add known old files
        for old_file_name in self.KNOWN_OLD_FILES:
            old_file_path = self.root_path / old_file_name
            if old_file_path.exists() and old_file_path not in unused_files:
                unused_files.add(old_file_path)

        if unused_files:
            print(f"Found {len(unused_files)} unused file(s):\n")
            for file_path in sorted(unused_files):
                rel_path = file_path.relative_to(self.root_path)
                print(f"  - {rel_path}")

                if not dry_run:
                    # Rename to .old
                    old_path = file_path.with_suffix(file_path.suffix + '.old')
                    file_path.rename(old_path)

                    # Move to old/ folder
                    dest = old_dir / old_path.name
                    shutil.move(str(old_path), str(dest))
                    print(f"    -> Moved to old/{old_path.name}")
            print()
        else:
            print("  [OK] No unused files found\n")

        # Step 2: Find and move test scripts
        print("[TESTS] Finding test scripts...\n")
        test_scripts = self.find_test_scripts()

        if test_scripts:
            print(f"Found {len(test_scripts)} test script(s):\n")
            for file_path in sorted(test_scripts):
                rel_path = file_path.relative_to(self.root_path)
                print(f"  - {rel_path}")

                if not dry_run:
                    dest = test_dir / file_path.name
                    shutil.move(str(file_path), str(dest))
                    print(f"    -> Moved to test_scripts/{file_path.name}")
            print()
        else:
            print("  [OK] No test scripts found in root\n")

        # Summary
        print("-" * 60)
        if dry_run:
            print("\n[INFO] This was a DRY RUN. No files were actually moved.")
            print("   Run without --dry-run to perform the cleanup.\n")
        else:
            print("\n[DONE] Cleanup complete!\n")
            print(f"[SUMMARY]")
            print(f"  - Files moved to old/: {len(unused_files)}")
            print(f"  - Test scripts organized: {len(test_scripts)}")
            print(f"\n  Total files in old/: {len(list(old_dir.glob('*')))}")
            print(f"  Total files in test_scripts/: {len(list(test_dir.glob('*')))}\n")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cleanup and organize project files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Root path to analyze (default: parent directory of script)"
    )

    args = parser.parse_args()

    # Determine root path: use parent directory if no path specified
    if args.path is None:
        script_dir = Path(__file__).resolve().parent
        root_path = script_dir.parent
    else:
        root_path = args.path

    # Run cleanup
    cleanup = ProjectCleanup(root_path)
    cleanup.cleanup(dry_run=args.dry_run)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())

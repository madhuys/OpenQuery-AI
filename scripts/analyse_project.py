#!/usr/bin/env python3
"""
Comprehensive Project Analysis Tool

Analyzes and generates complete project documentation including:
- Directory structure with LOC
- File statistics
- Codebase map (functions, classes, constants)
- Variable analysis (comprehensive)
- Summary statistics

Outputs: PROJECT_STRUCTURE.md (single comprehensive file)
"""

import os
import sys
import ast
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
import mimetypes


class CodebaseMapper(ast.NodeVisitor):
    """AST visitor to map all code elements (functions, classes, constants, variables)"""

    def __init__(self, filename: str):
        self.filename = filename

        # Code structure
        self.functions: List[Tuple[str, int, List[str]]] = []  # (name, line, params)
        self.classes: List[Tuple[str, int, List[str]]] = []  # (name, line, methods)
        self.constants: List[Tuple[str, int]] = []
        self.globals: List[Tuple[str, int]] = []

        # Variable tracking for detailed analysis
        self.function_params: List[Tuple[str, str, int]] = []  # (param, function, line)
        self.local_vars: List[Tuple[str, str, int]] = []
        self.class_attrs: List[Tuple[str, str, int]] = []
        self.imports: List[Tuple[str, int]] = []

        self.current_function: str = None
        self.current_class: str = None
        self.current_class_methods: List[str] = []

    def visit_Import(self, node):
        """Visit import statements"""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports.append((name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Visit from...import statements"""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports.append((name, node.lineno))
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Visit function definitions"""
        previous_function = self.current_function
        self.current_function = node.name

        # Extract parameters
        params = [arg.arg for arg in node.args.args]

        # Record function
        if self.current_class:
            # Method in class
            self.current_class_methods.append(node.name)
        else:
            # Module-level function
            self.functions.append((node.name, node.lineno, params))

        # Record parameters for variable analysis
        for arg in node.args.args:
            if arg.arg not in ('self', 'cls'):
                self.function_params.append((arg.arg, node.name, node.lineno))

        # Visit function body
        self.generic_visit(node)

        self.current_function = previous_function

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definitions"""
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        """Visit class definitions"""
        previous_class = self.current_class
        previous_methods = self.current_class_methods

        self.current_class = node.name
        self.current_class_methods = []

        # Visit class body
        self.generic_visit(node)

        # Record class with its methods
        self.classes.append((node.name, node.lineno, self.current_class_methods.copy()))

        self.current_class = previous_class
        self.current_class_methods = previous_methods

    def visit_Assign(self, node):
        """Visit assignment statements"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id

                # Categorize the variable
                if self.current_function:
                    # Local variable in function
                    self.local_vars.append((var_name, self.current_function, node.lineno))
                elif self.current_class:
                    # Class attribute
                    self.class_attrs.append((var_name, self.current_class, node.lineno))
                else:
                    # Module-level variable
                    if var_name.isupper() and not var_name.startswith('_'):
                        self.constants.append((var_name, node.lineno))
                    elif not var_name.startswith('_'):
                        self.globals.append((var_name, node.lineno))

            elif isinstance(target, ast.Attribute):
                # Handle self.attr = value
                if isinstance(target.value, ast.Name):
                    if target.value.id in ('self', 'cls') and self.current_class:
                        self.class_attrs.append((target.attr, self.current_class, node.lineno))

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        """Visit annotated assignment statements"""
        if isinstance(node.target, ast.Name):
            var_name = node.target.id

            if self.current_function:
                self.local_vars.append((var_name, self.current_function, node.lineno))
            elif self.current_class:
                self.class_attrs.append((var_name, self.current_class, node.lineno))
            else:
                if var_name.isupper() and not var_name.startswith('_'):
                    self.constants.append((var_name, node.lineno))
                elif not var_name.startswith('_'):
                    self.globals.append((var_name, node.lineno))

        self.generic_visit(node)


class ProjectAnalyzer:
    """Analyzes project structure and generates comprehensive markdown documentation"""

    # Directories to ignore
    IGNORE_DIRS = {
        '.git', '__pycache__', 'node_modules', '.next', 'venv', 'env',
        '.venv', 'dist', 'build', '.pytest_cache', '.mypy_cache',
        '.tox', 'htmlcov', '.coverage', 'eggs', '.eggs',
        '*.egg-info', 'old', 'test_scripts', 'logs', 'reference documentation'
    }

    # File extensions to ignore
    IGNORE_EXTENSIONS = {
        '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib',
        '.exe', '.bin', '.dat', '.db', '.sqlite', '.sqlite3',
        '.log', '.tmp', '.temp', '.bak', '.swp', '.swo',
        '.DS_Store', '.gitkeep', '.db-shm', '.db-wal'
    }

    # File patterns to ignore
    IGNORE_PATTERNS = {
        '.gitignore', '.env', '.env.local', '.env.production',
        'Thumbs.db', 'desktop.ini'
    }

    # Code file extensions to count LOC
    CODE_EXTENSIONS = {
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c',
        '.h', '.hpp', '.cs', '.rb', '.go', '.rs', '.php', '.swift',
        '.kt', '.scala', '.sh', '.bash', '.zsh', '.fish', '.sql',
        '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte'
    }

    # Config/data file extensions
    CONFIG_EXTENSIONS = {
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.xml', '.md', '.txt', '.rst', '.csv'
    }

    def __init__(self, root_path: str = "."):
        """Initialize analyzer with root path"""
        self.root_path = Path(root_path).resolve()
        self.file_stats: Dict[str, int] = {}
        self.extension_counts: Dict[str, int] = {}
        self.total_loc = 0
        self.total_files = 0
        self.total_dirs = 0

        # Codebase mapping storage
        self.all_functions: Dict[str, List[Tuple[str, int, List[str]]]] = defaultdict(list)
        self.all_classes: Dict[str, List[Tuple[str, int, List[str]]]] = defaultdict(list)
        self.all_constants: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.all_globals: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

        # Variable analysis storage
        self.all_function_params: Dict[str, List[Tuple[str, str, int]]] = defaultdict(list)
        self.all_local_vars: Dict[str, List[Tuple[str, str, int]]] = defaultdict(list)
        self.all_class_attrs: Dict[str, List[Tuple[str, str, int]]] = defaultdict(list)
        self.all_imports: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

    def should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored"""
        # Check if any parent directory is in ignore list
        for parent in path.parents:
            if parent.name in self.IGNORE_DIRS:
                return True

        # Check if directory itself should be ignored
        if path.is_dir() and path.name in self.IGNORE_DIRS:
            return True

        # Check file extension
        if path.suffix.lower() in self.IGNORE_EXTENSIONS:
            return True

        # Check file name patterns
        if path.name in self.IGNORE_PATTERNS:
            return True

        return False

    def count_lines(self, file_path: Path) -> int:
        """Count non-empty lines in a file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Count non-empty lines (strip whitespace)
                return sum(1 for line in lines if line.strip())
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
            return 0

    def analyze_file(self, file_path: Path) -> Dict:
        """Analyze a single file and return stats"""
        stats = {
            'path': file_path,
            'size': file_path.stat().st_size,
            'extension': file_path.suffix.lower(),
            'loc': 0,
            'type': 'unknown'
        }

        # Determine file type
        if stats['extension'] in self.CODE_EXTENSIONS:
            stats['type'] = 'code'
            stats['loc'] = self.count_lines(file_path)
        elif stats['extension'] in self.CONFIG_EXTENSIONS:
            stats['type'] = 'config'
            stats['loc'] = self.count_lines(file_path)
        else:
            stats['type'] = 'other'

        # Update counters
        self.extension_counts[stats['extension']] = \
            self.extension_counts.get(stats['extension'], 0) + 1

        if stats['loc'] > 0:
            self.total_loc += stats['loc']

        self.total_files += 1

        return stats

    def analyze_python_file(self, file_path: Path):
        """Analyze Python file for code structure and variables"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            mapper = CodebaseMapper(file_path.name)
            mapper.visit(tree)

            # Store results
            filename = file_path.name
            self.all_functions[filename].extend(mapper.functions)
            self.all_classes[filename].extend(mapper.classes)
            self.all_constants[filename].extend(mapper.constants)
            self.all_globals[filename].extend(mapper.globals)
            self.all_function_params[filename].extend(mapper.function_params)
            self.all_local_vars[filename].extend(mapper.local_vars)
            self.all_class_attrs[filename].extend(mapper.class_attrs)
            self.all_imports[filename].extend(mapper.imports)

        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"Warning: Could not parse {file_path.name}: {e}", file=sys.stderr)

    def walk_directory(self, path: Path, prefix: str = "", is_last: bool = True) -> List[str]:
        """
        Recursively walk directory and generate tree structure
        Returns list of formatted tree lines
        """
        lines = []

        if self.should_ignore(path):
            return lines

        # Get all items in directory
        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return lines

        # Filter ignored items
        items = [item for item in items if not self.should_ignore(item)]

        for idx, item in enumerate(items):
            is_last_item = (idx == len(items) - 1)

            # Tree characters
            connector = "└── " if is_last_item else "├── "
            extension = "    " if is_last_item else "│   "

            if item.is_dir():
                self.total_dirs += 1
                lines.append(f"{prefix}{connector}{item.name}/")
                # Recurse into directory
                sub_lines = self.walk_directory(item, prefix + extension, is_last_item)
                lines.extend(sub_lines)
            else:
                # Analyze file
                stats = self.analyze_file(item)

                # Analyze Python files for code structure
                if item.suffix == '.py':
                    self.analyze_python_file(item)

                # Format: filename (LOC lines) [size]
                size_str = self.format_size(stats['size'])

                if stats['loc'] > 0:
                    file_info = f"{item.name} ({stats['loc']} lines) [{size_str}]"
                else:
                    file_info = f"{item.name} [{size_str}]"

                lines.append(f"{prefix}{connector}{file_info}")

        return lines

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

    def generate_summary(self) -> List[str]:
        """Generate summary statistics"""
        lines = []
        lines.append("## Project Statistics")
        lines.append("")
        lines.append(f"- **Total Files**: {self.total_files}")
        lines.append(f"- **Total Directories**: {self.total_dirs}")
        lines.append(f"- **Total Lines of Code**: {self.total_loc:,}")
        lines.append("")

        # Group by file type
        lines.append("### Files by Extension")
        lines.append("")

        # Sort extensions by count
        sorted_extensions = sorted(
            self.extension_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for ext, count in sorted_extensions:
            ext_name = ext if ext else "(no extension)"
            lines.append(f"- `{ext_name}`: {count} file{'s' if count != 1 else ''}")

        lines.append("")

        return lines

    def generate_codebase_map(self) -> List[str]:
        """Generate codebase map section"""
        lines = []
        lines.append("## Codebase Map")
        lines.append("")

        # Functions
        if self.all_functions:
            lines.append("### Functions")
            lines.append("")
            for filename, funcs in sorted(self.all_functions.items()):
                if funcs:
                    lines.append(f"**{filename}**")
                    for name, line, params in sorted(funcs, key=lambda x: x[1]):
                        param_str = ", ".join(params) if params else ""
                        lines.append(f"- `{name}({param_str})` → line {line}")
                    lines.append("")

        # Classes
        if self.all_classes:
            lines.append("### Classes")
            lines.append("")
            for filename, classes in sorted(self.all_classes.items()):
                if classes:
                    lines.append(f"**{filename}**")
                    for name, line, methods in sorted(classes, key=lambda x: x[1]):
                        method_str = ", ".join(methods[:5]) if methods else "no methods"
                        if len(methods) > 5:
                            method_str += f", ... (+{len(methods)-5} more)"
                        lines.append(f"- `{name}` → line {line} (methods: {method_str})")
                    lines.append("")

        # Constants
        if self.all_constants:
            lines.append("### Constants")
            lines.append("")
            # Collect unique constants
            unique_constants = {}
            for filename, consts in self.all_constants.items():
                for const, line in consts:
                    if const not in unique_constants:
                        unique_constants[const] = []
                    unique_constants[const].append((filename, line))

            for const in sorted(unique_constants.keys()):
                locations = unique_constants[const]
                loc_str = ", ".join([f"{fn}:{ln}" for fn, ln in locations])
                lines.append(f"- `{const}` → {loc_str}")
            lines.append("")

        return lines

    def generate_variable_analysis(self) -> List[str]:
        """Generate comprehensive variable analysis"""
        lines = []
        lines.append("## Variable Analysis")
        lines.append("")

        # Summary statistics
        unique_params = set()
        unique_locals = set()
        unique_attrs = set()
        unique_imports = set()

        for params_list in self.all_function_params.values():
            for param, _, _ in params_list:
                unique_params.add(param)

        for locals_list in self.all_local_vars.values():
            for var, _, _ in locals_list:
                unique_locals.add(var)

        for attrs_list in self.all_class_attrs.values():
            for attr, _, _ in attrs_list:
                unique_attrs.add(attr)

        for imports_list in self.all_imports.values():
            for imp, _ in imports_list:
                unique_imports.add(imp)

        lines.append("### Statistics")
        lines.append("")
        lines.append(f"- **Unique Parameters**: {len(unique_params)}")
        lines.append(f"- **Unique Local Variables**: {len(unique_locals)}")
        lines.append(f"- **Unique Class Attributes**: {len(unique_attrs)}")
        lines.append(f"- **Unique Imports**: {len(unique_imports)}")
        lines.append("")

        # Most common parameters
        param_counts = defaultdict(int)
        for params_list in self.all_function_params.values():
            for param, _, _ in params_list:
                param_counts[param] += 1

        if param_counts:
            lines.append("### Most Common Parameters")
            lines.append("")
            top_params = sorted(param_counts.items(), key=lambda x: x[1], reverse=True)[:15]
            for param, count in top_params:
                lines.append(f"- `{param}` (used {count} times)")
            lines.append("")

        # Naming patterns
        all_names = unique_params | unique_locals | unique_attrs
        snake_case = [n for n in all_names if '_' in n and n.islower()]
        camel_case = [n for n in all_names if not '_' in n and any(c.isupper() for c in n[1:])]
        single_char = [n for n in all_names if len(n) == 1]

        lines.append("### Naming Patterns")
        lines.append("")
        lines.append(f"- **snake_case**: {len(snake_case)} variables")
        lines.append(f"- **camelCase/PascalCase**: {len(camel_case)} variables")
        lines.append(f"- **Single character**: {len(single_char)} variables")
        lines.append("")

        return lines

    def analyze(self) -> str:
        """
        Analyze project and return markdown formatted output
        """
        lines = []

        # Header
        lines.append(f"# Project Structure: {self.root_path.name}")
        lines.append("")
        lines.append(f"**Root Path**: `{self.root_path}`")
        lines.append("")
        lines.append("**Auto-generated** by `analyse_project.py` - Do not edit manually")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Directory tree
        lines.append("## Directory Tree")
        lines.append("")
        lines.append("```")
        lines.append(f"{self.root_path.name}/")

        # Walk directory
        tree_lines = self.walk_directory(self.root_path)
        lines.extend(tree_lines)

        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Summary
        summary_lines = self.generate_summary()
        lines.extend(summary_lines)

        lines.append("---")
        lines.append("")

        # Codebase map
        codebase_lines = self.generate_codebase_map()
        lines.extend(codebase_lines)

        lines.append("---")
        lines.append("")

        # Variable analysis
        var_lines = self.generate_variable_analysis()
        lines.extend(var_lines)

        return "\n".join(lines)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Comprehensive project analysis - generates PROJECT_STRUCTURE.md"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Root path to analyze (default: parent directory of script)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file path (default: PROJECT_STRUCTURE.md in root)"
    )

    args = parser.parse_args()

    # Determine root path: use parent directory if no path specified
    if args.path is None:
        script_dir = Path(__file__).resolve().parent
        root_path = script_dir.parent
    else:
        root_path = Path(args.path)

    # Determine output path: use root directory if not specified
    if args.output is None:
        output_path = root_path / "PROJECT_STRUCTURE.md"
    else:
        output_path = Path(args.output)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Analyze project
    print("🔍 Analyzing project structure...", file=sys.stderr)
    analyzer = ProjectAnalyzer(root_path)
    markdown_output = analyzer.analyze()

    # Write output file
    output_path.write_text(markdown_output, encoding='utf-8')

    print(f"✅ Analysis complete!", file=sys.stderr)
    print(f"   Output: {output_path}", file=sys.stderr)
    print(f"   Total files: {analyzer.total_files}", file=sys.stderr)
    print(f"   Total LOC: {analyzer.total_loc:,}", file=sys.stderr)
    print(f"   Functions: {sum(len(f) for f in analyzer.all_functions.values())}", file=sys.stderr)
    print(f"   Classes: {sum(len(c) for c in analyzer.all_classes.values())}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

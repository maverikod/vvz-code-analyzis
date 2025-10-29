# Code Analysis Tool

A comprehensive Python code analysis tool that generates code maps, detects issues, and provides detailed reports.

## Features

- **Code Mapping**: Generates comprehensive maps of classes, functions, and dependencies
- **Issue Detection**: Identifies code quality problems and violations
- **Multiple Report Formats**: Outputs reports in YAML format
- **Configurable Analysis**: Customizable file size limits and analysis parameters
- **CLI Interface**: Easy-to-use command-line interface

## Installation

### From PyPI (recommended)

```bash
pip install code-analysis-tool
```

### From source

```bash
git clone https://github.com/vasilyvz/code-analysis-tool.git
cd code-analysis-tool
pip install -e .
```

## Usage

### Basic usage

```bash
code-analysis
```

This will analyze the current directory and generate reports in the `code_analysis` folder.

### Advanced usage

```bash
code-analysis --root-dir ./src --output-dir ./reports --max-lines 500 --verbose
```

### Command line options

- `--root-dir, -r`: Root directory to analyze (default: current directory)
- `--output-dir, -o`: Output directory for reports (default: code_analysis)
- `--max-lines, -m`: Maximum lines per file (default: 400)
- `--verbose, -v`: Enable verbose output
- `--version`: Show version information

## Output Files

The tool generates the following files in the output directory:

- `code_map.yaml`: Complete code map with classes, functions, and dependencies
- `code_issues.yaml`: Detailed report of code quality issues
- `method_index.yaml`: Index of methods organized by class

## Detected Issues

The tool detects various code quality issues:

- Files without docstrings
- Classes without docstrings
- Methods without docstrings
- Methods with only `pass` statements
- `NotImplementedError` in non-abstract methods
- Files exceeding line limit
- Usage of `Any` type annotations
- Generic exception handling
- Imports in the middle of files

## Development

### Setup development environment

```bash
git clone https://github.com/vasilyvz/code-analysis-tool.git
cd code-analysis-tool
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
```

### Code formatting

```bash
black .
flake8 .
mypy .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run the linters and fix any issues
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

**Vasiliy Zdanovskiy**
- Email: vasilyvz@gmail.com
- GitHub: [@vasilyvz](https://github.com/vasilyvz)

## Changelog

### 1.0.0
- Initial release
- Basic code analysis functionality
- CLI interface
- YAML report generation
- Issue detection

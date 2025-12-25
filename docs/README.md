# Code Analysis Tool

A comprehensive Python code analysis and refactoring tool that generates code maps, detects issues, and provides automated refactoring capabilities.

Author: Vasiliy Zdanovskiy  
Email: vasilyvz@gmail.com

## Features

### Code Analysis
- **Code Mapping**: Generates comprehensive maps of classes, functions, and dependencies
- **Issue Detection**: Identifies code quality problems and violations
- **SQLite Database**: Fast indexed storage for large codebases (default)
- **YAML Export**: Optional YAML format for compatibility
- **Configurable Analysis**: Customizable file size limits and analysis parameters
- **CLI Interface**: Easy-to-use command-line interface

### Code Refactoring
- **Class Splitting**: Split large classes into smaller components
- **Superclass Extraction**: Extract common functionality into base classes
- **Class Merging**: Merge multiple classes into a single base class
- **Safety Checks**: Automatic backups, validation, and rollback on errors
- **Strict Completeness Validation**: Pre-collects all methods and properties before operation, then validates they are all present after refactoring

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

### Code Analysis

#### Basic usage

```bash
code_mapper
```

This will analyze the current directory and generate reports in the `code_analysis` folder.

#### Advanced usage

```bash
code_mapper --root-dir ./src --output-dir ./reports --max-lines 500 --verbose
```

#### Command line options

- `--root-dir, -r`: Root directory to analyze (default: current directory)
- `--output-dir, -o`: Output directory for reports (default: code_analysis)
- `--max-lines, -m`: Maximum lines per file (default: 400)
- `--verbose, -v`: Enable verbose output
- `--use-sqlite/--no-sqlite`: Use SQLite database (default: True)
- `--version`: Show version information

#### Output Files

**SQLite Mode (default):**
- `code_analysis.db`: SQLite database with all analysis data
  - Fast indexed searches
  - SQL queries for complex filtering
  - Single file storage

**YAML Mode (`--no-sqlite`):**
- `code_map.yaml`: Complete code map with classes, functions, and dependencies
- `code_issues.yaml`: Detailed report of code quality issues
- `method_index.yaml`: Index of methods organized by class

#### Detected Issues

The tool detects various code quality issues:

- Files without docstrings
- Classes without docstrings
- Methods without docstrings
- Methods with only `pass` statements
- `NotImplementedError` in non-abstract methods
- Files exceeding line limit
- Usage of `Any` type annotations
- Generic exception handling
- Invalid imports
- Imports in the middle of files

## CST-based module composition (logical blocks)

If you want to refactor by **logical blocks** (preserving comments, moving imports to the top,
validating via `compile()`), see `docs/CST_TOOLS.md`, `docs/CST_QUERY.md` and MCP commands
`compose_cst_module` / `query_cst`.

## Code Refactoring

### Class Splitting

Split a large class into multiple smaller classes while maintaining functionality.

#### Example: Before

```python
class UserManager:
    """Manages user operations."""
    
    def __init__(self):
        self.username = None
        self.email = None
        self.password = None
        self.role = None
        self.permissions = []
    
    def authenticate(self, username, password):
        """Authenticate user."""
        # ... authentication logic
    
    def authorize(self, action):
        """Check user permissions."""
        # ... authorization logic
    
    def send_email(self, subject, body):
        """Send email to user."""
        # ... email logic
```

#### Configuration File (`split_config.json`)

```json
{
  "src_class": "UserManager",
  "dst_classes": {
    "UserAuth": {
      "props": ["username", "email", "password"],
      "methods": ["authenticate"]
    },
    "UserPermissions": {
      "props": ["role", "permissions"],
      "methods": ["authorize"]
    },
    "UserEmail": {
      "props": [],
      "methods": ["send_email"]
    }
  }
}
```

#### Command

```bash
# Dry run (validate without changes)
code_refactor split-class -f user_manager.py -c split_config.json --dry-run

# Perform split
code_refactor split-class -f user_manager.py -c split_config.json
```

#### Example: After

```python
class UserManager:
    """Manages user operations."""
    
    def __init__(self):
        self.userauth = UserAuth()
        self.userpermissions = UserPermissions()
        self.useremail = UserEmail()
    
    def authenticate(self, username, password):
        return self.userauth.authenticate(username, password)
    
    def authorize(self, action):
        return self.userpermissions.authorize(action)
    
    def send_email(self, subject, body):
        return self.useremail.send_email(subject, body)

class UserAuth:
    """Handles user authentication."""
    
    def __init__(self):
        self.username = None
        self.email = None
        self.password = None
    
    def authenticate(self, username, password):
        """Authenticate user."""
        # ... authentication logic

class UserPermissions:
    """Manages user permissions."""
    
    def __init__(self):
        self.role = None
        self.permissions = []
    
    def authorize(self, action):
        """Check user permissions."""
        # ... authorization logic

class UserEmail:
    """Handles user email operations."""
    
    def __init__(self):
        pass
    
    def send_email(self, subject, body):
        """Send email to user."""
        # ... email logic
```

#### Safety Features

- **Automatic Backup**: Creates backup in `.code_mapper_backups/` before changes
- **Pre-Operation Validation**: Collects all methods and properties from source class BEFORE operation
- **Configuration Validation**: Checks that all properties and methods are accounted for in config
- **Python Syntax Check**: Validates syntax after splitting
- **Strict Completeness Check**: Compares pre-collected original members with refactored code to ensure ALL are present
- **Import Validation**: Verifies module can be imported (optional, warnings only)
- **Automatic Rollback**: Restores backup if any validation fails

### Class Merging

Merge multiple classes into a single base class. This is the inverse operation of extract-superclass.

#### Example: Before

```python
class UserAuth:
    """Handles user authentication."""
    
    def __init__(self):
        self.username = None
        self.password = None
    
    def login(self, username, password):
        """Authenticate user."""
        # ... login logic
        return True

class UserProfile:
    """Handles user profile operations."""
    
    def __init__(self):
        self.email = None
        self.name = None
    
    def update_profile(self, email, name):
        """Update user profile."""
        # ... profile logic
        return True

class UserSettings:
    """Handles user settings."""
    
    def __init__(self):
        self.theme = None
        self.language = None
    
    def update_settings(self, theme, language):
        """Update user settings."""
        # ... settings logic
        return True
```

#### Configuration File (`merge_config.json`)

```json
{
  "base_class": "UserService",
  "source_classes": ["UserAuth", "UserProfile", "UserSettings"],
  "merge_methods": ["login", "update_profile", "update_settings"],
  "merge_props": ["username", "password", "email", "name", "theme", "language"]
}
```

**Note**: `merge_methods` and `merge_props` are optional. If not specified, ALL methods and properties from source classes will be merged.

#### Command

```bash
# Dry run (validate without changes)
code_refactor merge-classes -f user_services.py -c merge_config.json --dry-run

# Perform merge
code_refactor merge-classes -f user_services.py -c merge_config.json
```

#### Example: After

```python
class UserService:
    """Merged class combining functionality from multiple classes."""
    
    def __init__(self):
        self.username = None
        self.password = None
        self.email = None
        self.name = None
        self.theme = None
        self.language = None
    
    def login(self, username, password):
        """Authenticate user."""
        # ... login logic
        return True
    
    def update_profile(self, email, name):
        """Update user profile."""
        # ... profile logic
        return True
    
    def update_settings(self, theme, language):
        """Update user settings."""
        # ... settings logic
        return True
```

#### Safety Features

- **Pre-Operation Collection**: Collects all methods and properties from ALL source classes BEFORE merge
- **Strict Validation**: Compares pre-collected members with merged class to ensure completeness
- **Automatic Backup**: Creates backup before changes
- **Python Syntax Check**: Validates syntax after merging
- **Automatic Rollback**: Restores backup if validation fails

### Superclass Extraction

Extract common functionality from multiple classes into a base class.

#### Example: Before

```python
class Dog:
    """Represents a dog."""
    
    def __init__(self, name):
        self.name = name
        self.species = "Canis lupus"
        self.legs = 4
    
    def make_sound(self):
        return "Woof!"
    
    def move(self):
        return f"{self.name} is running"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"

class Cat:
    """Represents a cat."""
    
    def __init__(self, name):
        self.name = name
        self.species = "Felis catus"
        self.legs = 4
    
    def make_sound(self):
        return "Meow!"
    
    def move(self):
        return f"{self.name} is walking"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"
```

#### Configuration File (`extract_config.json`)

```json
{
  "base_class": "Animal",
  "child_classes": ["Dog", "Cat"],
  "abstract_methods": ["make_sound"],
  "extract_from": {
    "Dog": {
      "properties": ["name", "species", "legs"],
      "methods": ["move", "eat"]
    },
    "Cat": {
      "properties": ["name", "species", "legs"],
      "methods": ["move", "eat"]
    }
  }
}
```

#### Command

```bash
# Dry run (validate without changes)
code_refactor extract-superclass -f animals.py -c extract_config.json --dry-run

# Perform extraction
code_refactor extract-superclass -f animals.py -c extract_config.json
```

#### Example: After

```python
from abc import ABC, abstractmethod

class Animal(ABC):
    """Base class for extracted functionality."""
    
    def __init__(self):
        self.name = None
        self.species = None
        self.legs = None
    
    def move(self):
        return f"{self.name} is moving"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"
    
    @abstractmethod
    def make_sound(self):
        pass

class Dog(Animal):
    """Represents a dog."""
    
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.species = "Canis lupus"
        self.legs = 4
    
    def make_sound(self):
        return "Woof!"
    
    def move(self):
        return f"{self.name} is running"

class Cat(Animal):
    """Represents a cat."""
    
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.species = "Felis catus"
        self.legs = 4
    
    def make_sound(self):
        return "Meow!"
    
    def move(self):
        return f"{self.name} is walking"
```

#### Safety Features

- **Multiple Inheritance Check**: Detects and prevents MRO conflicts
- **Method Compatibility**: Validates that methods have compatible signatures
- **Automatic Backup**: Creates backup before changes
- **Python Syntax Check**: Validates syntax after extraction
- **Completeness Check**: Ensures inheritance is correctly set up
- **Import Validation**: Verifies module can be imported
- **Automatic Rollback**: Restores backup if any validation fails

#### Configuration Format

```json
{
  "base_class": "BaseClassName",
  "child_classes": ["ChildClass1", "ChildClass2"],
  "abstract_methods": ["method1", "method2"],
  "extract_from": {
    "ChildClass1": {
      "properties": ["prop1", "prop2"],
      "methods": ["method1", "method2"]
    },
    "ChildClass2": {
      "properties": ["prop3"],
      "methods": ["method3"]
    }
  }
}
```

**Fields:**
- `base_class`: Name of the new base class to create
- `child_classes`: List of existing classes that will inherit from base class
- `abstract_methods`: List of method names that will be abstract in base class
- `extract_from`: Dictionary mapping child class names to their extracted elements
  - `properties`: List of property names to extract to base class
  - `methods`: List of method names to extract to base class

**Requirements:**
- All child classes must exist in the same file
- Methods with the same name must have compatible signatures across classes
- Child classes must not already have base classes (to avoid MRO conflicts)
- Base class name must not already exist

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

## Changelog

### 1.0.4
- **IMPROVED**: Strict completeness validation - pre-collects all methods and properties BEFORE operation, then validates they are all present after refactoring
- **NEW**: Class merging functionality - merge multiple classes into a single base class
- **NEW**: `merge-classes` CLI command for class merging operations
- Enhanced validation error messages with counts of original vs found members
- Improved documentation with examples for all refactoring operations

### 1.0.3
- Added SQLite database support for faster analysis
- Added class splitting refactoring functionality
- Added superclass extraction refactoring functionality
- Enhanced safety with automatic backups and validation
- Improved documentation

### 1.0.2
- Changed console command name from `code-analysis` to `code_mapper`
- Fixed .gitignore to properly track source code directory
- All code quality checks passed

### 1.0.1
- Package configuration improvements
- Enhanced documentation

### 1.0.0
- Initial release
- Basic code analysis functionality
- CLI interface
- YAML report generation
- Issue detection

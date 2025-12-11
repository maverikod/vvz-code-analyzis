"""
Documentation generator for vector store commands.

This module provides automatic generation of documentation from command metadata,
including API documentation, examples, and usage guides.

Features:
- Automatic API documentation generation
- Example code generation
- Usage guide creation
- Markdown and HTML output formats
- Integration with command metadata

Architecture:
- Template-based documentation generation
- Metadata-driven content creation
- Multiple output formats support
- Extensible template system

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("vector_store.utils.documentation_generator")


class DocumentationGenerator:
    """
    Generator for automatic documentation from command metadata.
    
    Creates comprehensive documentation including API references,
    examples, and usage guides from command metadata.
    
    Features:
    - Markdown documentation generation
    - HTML documentation generation
    - API reference creation
    - Example code generation
    - Usage guide creation
    """
    
    def __init__(self, output_dir: str = "docs/generated") -> None:
        """
        Initialize documentation generator.
        
        Args:
            output_dir: Output directory for generated documentation
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Template directories
        self.template_dir = Path(__file__).parent.parent / "templates" / "docs"
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # Output formats
        self.formats = ["markdown", "html"]
        
        self.logger = logger
    
    def generate_all_documentation(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Generate all documentation formats.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Dictionary of generated file paths
        """
        generated_files = {}
        
        for format_type in self.formats:
            try:
                if format_type == "markdown":
                    file_path = self.generate_markdown_docs(commands_metadata)
                elif format_type == "html":
                    file_path = self.generate_html_docs(commands_metadata)
                
                generated_files[format_type] = str(file_path)
                self.logger.info(f"Generated {format_type} documentation: {file_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to generate {format_type} documentation: {e}")
                generated_files[format_type] = None
        
        return generated_files
    
    def generate_markdown_docs(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> Path:
        """
        Generate Markdown documentation.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Path to generated markdown file
        """
        output_file = self.output_dir / "api_reference.md"
        
        content = self._generate_markdown_content(commands_metadata)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_file
    
    def generate_html_docs(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> Path:
        """
        Generate HTML documentation.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Path to generated HTML file
        """
        output_file = self.output_dir / "api_reference.html"
        
        content = self._generate_html_content(commands_metadata)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_file
    
    def _generate_markdown_content(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Generate Markdown content from command metadata.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Markdown content string
        """
        content = [
            "# Vector Store API Reference",
            "",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "## Overview",
            "",
            "This document provides a comprehensive reference for all vector store commands.",
            "",
            "## Commands",
            ""
        ]
        
        # Sort commands by category
        main_commands = []
        auxiliary_commands = []
        system_commands = []
        
        for command_name, metadata in commands_metadata.items():
            if command_name in ["chunk_create", "search_records", "chunk_delete", "count", "info"]:
                main_commands.append((command_name, metadata))
            elif command_name in ["find_duplicate_uuids", "force_delete_by_uuids", "hard_delete"]:
                auxiliary_commands.append((command_name, metadata))
            else:
                system_commands.append((command_name, metadata))
        
        # Main commands
        if main_commands:
            content.extend([
                "### Main Commands",
                ""
            ])
            for command_name, metadata in sorted(main_commands):
                content.extend(self._generate_command_markdown(command_name, metadata))
        
        # Auxiliary commands
        if auxiliary_commands:
            content.extend([
                "### Auxiliary Commands",
                ""
            ])
            for command_name, metadata in sorted(auxiliary_commands):
                content.extend(self._generate_command_markdown(command_name, metadata))
        
        # System commands
        if system_commands:
            content.extend([
                "### System Commands",
                ""
            ])
            for command_name, metadata in sorted(system_commands):
                content.extend(self._generate_command_markdown(command_name, metadata))
        
        return "\n".join(content)
    
    def _generate_command_markdown(
        self,
        command_name: str,
        metadata: Dict[str, Any]
    ) -> List[str]:
        """
        Generate Markdown content for a single command.
        
        Args:
            command_name: Name of the command
            metadata: Command metadata
            
        Returns:
            List of markdown lines
        """
        content = [
            f"#### {command_name}",
            "",
            f"**{metadata.get('description', 'No description available')}**",
            ""
        ]
        
        # Parameters
        if "params" in metadata and metadata["params"]:
            content.extend([
                "**Parameters:**",
                ""
            ])
            
            params = metadata["params"]
            if "properties" in params:
                for param_name, param_schema in params["properties"].items():
                    param_type = param_schema.get("type", "any")
                    param_desc = param_schema.get("description", "No description")
                    required = param_name in params.get("required", [])
                    
                    required_text = " (required)" if required else " (optional)"
                    content.append(f"- `{param_name}` ({param_type}){required_text}: {param_desc}")
            
            content.append("")
        
        # Examples
        if "examples" in metadata and metadata["examples"]:
            content.extend([
                "**Examples:**",
                ""
            ])
            
            examples = metadata["examples"]
            if "success" in examples:
                content.extend([
                    "Success:",
                    "```json",
                    json.dumps(examples["success"], indent=2),
                    "```",
                    ""
                ])
            
            if "error" in examples:
                content.extend([
                    "Error:",
                    "```json",
                    json.dumps(examples["error"], indent=2),
                    "```",
                    ""
                ])
        
        # Error codes
        if "error_codes" in metadata and metadata["error_codes"]:
            content.extend([
                "**Error Codes:**",
                ""
            ])
            
            for error_code in metadata["error_codes"]:
                code = error_code.get("code", "unknown")
                description = error_code.get("description", "No description")
                when = error_code.get("when", "Unknown")
                
                content.extend([
                    f"- `{code}`: {description}",
                    f"  - When: {when}",
                    ""
                ])
        
        content.append("---")
        content.append("")
        
        return content
    
    def _generate_html_content(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Generate HTML content from command metadata.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            HTML content string
        """
        html_content = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "    <title>Vector Store API Reference</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif; margin: 40px; }",
            "        .command { margin-bottom: 30px; border: 1px solid #ddd; padding: 20px; border-radius: 5px; }",
            "        .command h3 { color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; }",
            "        .parameter { margin: 10px 0; padding: 10px; background-color: #f9f9f9; border-radius: 3px; }",
            "        .example { margin: 10px 0; }",
            "        .example pre { background-color: #f4f4f4; padding: 10px; border-radius: 3px; overflow-x: auto; }",
            "        .error-code { margin: 5px 0; color: #d32f2f; }",
            "        .required { color: #d32f2f; font-weight: bold; }",
            "        .optional { color: #1976d2; }",
            "    </style>",
            "</head>",
            "<body>",
            f"    <h1>Vector Store API Reference</h1>",
            f"    <p><em>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>",
            "    <p>This document provides a comprehensive reference for all vector store commands.</p>",
            ""
        ]
        
        # Generate command sections
        for command_name, metadata in sorted(commands_metadata.items()):
            html_content.extend(self._generate_command_html(command_name, metadata))
        
        html_content.extend([
            "</body>",
            "</html>"
        ])
        
        return "\n".join(html_content)
    
    def _generate_command_html(
        self,
        command_name: str,
        metadata: Dict[str, Any]
    ) -> List[str]:
        """
        Generate HTML content for a single command.
        
        Args:
            command_name: Name of the command
            metadata: Command metadata
            
        Returns:
            List of HTML lines
        """
        content = [
            f"    <div class='command'>",
            f"        <h3>{command_name}</h3>",
            f"        <p><strong>{metadata.get('description', 'No description available')}</strong></p>"
        ]
        
        # Parameters
        if "params" in metadata and metadata["params"]:
            content.extend([
                "        <h4>Parameters:</h4>"
            ])
            
            params = metadata["params"]
            if "properties" in params:
                for param_name, param_schema in params["properties"].items():
                    param_type = param_schema.get("type", "any")
                    param_desc = param_schema.get("description", "No description")
                    required = param_name in params.get("required", [])
                    
                    required_class = "required" if required else "optional"
                    required_text = " (required)" if required else " (optional)"
                    
                    content.extend([
                        f"        <div class='parameter'>",
                        f"            <span class='{required_class}'>{param_name}</span> ({param_type}){required_text}: {param_desc}",
                        f"        </div>"
                    ])
        
        # Examples
        if "examples" in metadata and metadata["examples"]:
            content.extend([
                "        <h4>Examples:</h4>"
            ])
            
            examples = metadata["examples"]
            if "success" in examples:
                content.extend([
                    "        <div class='example'>",
                    "            <strong>Success:</strong>",
                    "            <pre>" + json.dumps(examples["success"], indent=2) + "</pre>",
                    "        </div>"
                ])
            
            if "error" in examples:
                content.extend([
                    "        <div class='example'>",
                    "            <strong>Error:</strong>",
                    "            <pre>" + json.dumps(examples["error"], indent=2) + "</pre>",
                    "        </div>"
                ])
        
        # Error codes
        if "error_codes" in metadata and metadata["error_codes"]:
            content.extend([
                "        <h4>Error Codes:</h4>"
            ])
            
            for error_code in metadata["error_codes"]:
                code = error_code.get("code", "unknown")
                description = error_code.get("description", "No description")
                when = error_code.get("when", "Unknown")
                
                content.extend([
                    f"        <div class='error-code'>",
                    f"            <strong>{code}</strong>: {description}<br>",
                    f"            <em>When: {when}</em>",
                    f"        </div>"
                ])
        
        content.append("    </div>")
        content.append("")
        
        return content
    
    def generate_examples_file(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> Path:
        """
        Generate examples file with all command examples.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Path to generated examples file
        """
        output_file = self.output_dir / "examples.md"
        
        content = [
            "# Vector Store Command Examples",
            "",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "This document contains practical examples for all vector store commands.",
            ""
        ]
        
        for command_name, metadata in sorted(commands_metadata.items()):
            content.extend([
                f"## {command_name}",
                "",
                f"{metadata.get('description', 'No description available')}",
                ""
            ])
            
            if "examples" in metadata and metadata["examples"]:
                examples = metadata["examples"]
                
                if "success" in examples:
                    content.extend([
                        "### Success Example",
                        "",
                        "```json",
                        json.dumps(examples["success"], indent=2),
                        "```",
                        ""
                    ])
                
                if "error" in examples:
                    content.extend([
                        "### Error Example",
                        "",
                        "```json",
                        json.dumps(examples["error"], indent=2),
                        "```",
                        ""
                    ])
            
            content.append("---")
            content.append("")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(content))
        
        return output_file
    
    def generate_schemas_file(
        self,
        commands_metadata: Dict[str, Dict[str, Any]]
    ) -> Path:
        """
        Generate schemas file with all command schemas.
        
        Args:
            commands_metadata: Dictionary of command metadata
            
        Returns:
            Path to generated schemas file
        """
        output_file = self.output_dir / "schemas.json"
        
        schemas = {}
        for command_name, metadata in commands_metadata.items():
            schemas[command_name] = {
                "params": metadata.get("params", {}),
                "result_schema": metadata.get("result_schema", {}),
                "error_schema": metadata.get("error_schema", {})
            }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(schemas, f, indent=2)
        
        return output_file 
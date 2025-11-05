"""
Setup script for code-analysis tool.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [
        line.strip()
        for line in fh
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="code-analysis-tool",
    version="1.0.2",
    author="Vasiliy Zdanovskiy",
    author_email="vasilyvz@gmail.com",
    description="A comprehensive Python code analysis tool that generates code maps and detects issues",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vasilyvz/code-analysis-tool",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "code_mapper=code_analysis.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)

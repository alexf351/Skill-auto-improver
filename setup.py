"""
Skill Auto-Improver - Autonomous Skill Improvement Pipeline

Setup configuration with zero external dependencies.
All functionality relies only on Python standard library.
"""

from setuptools import setup, find_packages

setup(
    name="skill-auto-improver",
    version="1.0.0",
    description="Autonomous MVP for improving user-built skills via observe-inspect-amend-evaluate loops",
    author="Jerry & Alex",
    author_email="jerry@example.com",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/skill-auto-improver",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        # ZERO external dependencies
        # All functionality uses only Python standard library:
        # - dataclasses (py3.7+)
        # - pathlib
        # - json
        # - subprocess
        # - difflib
        # - uuid
        # - zipfile
        # - datetime
    ],
    extras_require={
        "dev": [
            # Testing and development only (not required for runtime)
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="agents skills llm autonomy improvement evolution",
    entry_points={
        "console_scripts": [
            "skill-auto-improver=skill_auto_improver.cli:main",
        ],
    },
)

#!/usr/bin/env python3

import io
import os

from setuptools import find_packages, setup


# Get version
def read(*names, **kwargs):
    with io.open(
        os.path.join(os.path.dirname(__file__), *names), encoding=kwargs.get("encoding", "utf8")
    ) as fp:
        return fp.read()


readme = open("README.md").read()

# set the install requirements
install_requires = [
    "torch>=1.9",
    "torchvision",
    "torchaudio",
    "gpytorch>=1.5",
    "botorch>=0.5",
    "ax-platform>=0.2.0",
    "scikit-learn",
    "scipy",
    "pandas",
    "numpy",
    "click",
    "xarray",
    "sqlalchemy",
    "PyYAML",
]

# Run the setup
setup(
    name="boa",
    use_scm_version={"write_to": "boa/_version.py"},
    setup_requires=["setuptools_scm"],
    description="An implementation of Gaussian Processes in Pytorch",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Madeline Scyphers, Justine Missik",
    url="https://github.com/madeline-scyphers/boa",
    author_email="madelinescyphers@gmail.com, jemissik@gmail.com",
    project_urls={
        "Source": "https://github.com/madeline-scyphers/boa",
    },
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(exclude=["test", "test.*"]),
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require={
        "dev": ["black", "black[jupyter]", "isort", "flake8", "flakeheaven", "pytest", "invoke"],
        "docs": ["sphinx", "myst-nb", "pydata-sphinx-theme"],
        "examples": ["jupyter", "hvplot"],
    },
)

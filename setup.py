from setuptools import setup, find_packages
import pathlib

HERE = pathlib.Path(__file__).parent
README = (HERE / "README.md").read_text()

setup(
    name="tsmpy",
    version="0.9.0",
    author="uknfire",
    author_email="uknfire@gmail.com",
    description="An orthogonal layout algorithm, using TSM approach",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/uknfire/tsmpy",
    license_files=["LICENSE"],
    packages=find_packages(),
    keywords=[
        "Graph Drawing",
        "orthogonal",
        "layout",
        "graph",
    ],
    install_requires=["networkx", "pulp"],
    python_requires=">=3.6",
)

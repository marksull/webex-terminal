from setuptools import setup, find_packages

setup(
    name="webex-terminal",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "websockets",
        "prompt_toolkit",
        "pyyaml",
        "click",
    ],
    entry_points={
        "console_scripts": [
            "webex-terminal=webex_terminal.cli.main:main",
        ],
    },
    author="Your Name",
    author_email="mark@sullivans.id.au",
    description="A terminal client for Cisco Webex",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/webex-terminal",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
